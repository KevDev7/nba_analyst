#!/usr/bin/env python3
"""
Run Phase 6 play-by-play parity validation against pbpstats.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import boto3


REPO_ROOT = Path(__file__).resolve().parents[3]
SILVER_TRANSFORM_DIR = REPO_ROOT / "pipelines" / "athena" / "transform" / "silver"
PBPSTATS_DIR_CANDIDATES = (
    REPO_ROOT / "references" / "pbpstats",
    REPO_ROOT / "reference" / "pbpstats",
)
PBPSTATS_DIR = next((path for path in PBPSTATS_DIR_CANDIDATES if path.exists()), PBPSTATS_DIR_CANDIDATES[0])
TESTS_DIR = REPO_ROOT / "pipelines" / "athena" / "tests" / "silver"

import sys

for path in (SILVER_TRANSFORM_DIR, PBPSTATS_DIR, TESTS_DIR):
    if path == PBPSTATS_DIR and not path.exists():
        continue
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import build_silver_playbyplay_events as ours
from pbpstats.resources.enhanced_pbp import EndOfPeriod, FieldGoal, FreeThrow, Rebound, StartOfPeriod
from run_playbyplay_phase_1_3_parity import (
    DEFAULT_GAME_SET_CSV,
    ValidationEnhancedLoader,
    load_validation_games,
    pbpstats_boxscore_teams,
)
from pbpstats.data_loader.live.enhanced_pbp.web import LiveEnhancedPbpWebLoader


PHASE6_FIELDS = [
    "teamStartingPeriodWithBall",
    "isPeriodStartEvent",
    "isPeriodEndEvent",
    "linkedShotActionNumber",
    "reboundOfMissedShotFlag",
    "freeThrowTripSequenceNum",
    "freeThrowTripSize",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game-set-csv",
        type=Path,
        default=DEFAULT_GAME_SET_CSV,
        help="CSV of validation game_ids.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only validate the first N game_ids from the CSV.",
    )
    parser.add_argument(
        "--game-id",
        dest="game_ids",
        action="append",
        default=[],
        help="Optional explicit game_id to validate. Repeatable.",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=20,
        help="Maximum mismatch examples to print.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional path for JSON summary output.",
    )
    return parser.parse_args()


def row_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return row.get("period"), row.get("orderNumber"), row.get("actionNumber")


def pbpstats_free_throw_trip_sequence(event: Any) -> int | None:
    if not isinstance(event, FreeThrow):
        return None
    if event.is_ft_1_of_1 or event.is_ft_1_of_2 or event.is_ft_1_of_3 or event.is_ft_1pt:
        return 1
    if event.is_ft_2_of_2 or event.is_ft_2_of_3 or event.is_ft_2pt:
        return 2
    if event.is_ft_3_of_3 or event.is_ft_3pt:
        return 3
    return None


def rebound_linked_shot_action_number(event: Any) -> int | None:
    if not isinstance(event, Rebound):
        return None
    try:
        missed_shot = event.missed_shot
    except Exception:
        return None
    return getattr(missed_shot, "event_num", None)


def rebound_of_missed_shot_flag(event: Any) -> bool:
    if not isinstance(event, Rebound):
        return False
    try:
        missed_shot = event.missed_shot
    except Exception:
        return False
    if isinstance(missed_shot, FieldGoal):
        return not bool(getattr(missed_shot, "is_made", False))
    if isinstance(missed_shot, FreeThrow):
        return not bool(getattr(missed_shot, "is_made", False))
    return False


def pbpstats_event_row(event: Any) -> dict[str, Any]:
    return {
        "period": getattr(event, "period", None),
        "orderNumber": getattr(event, "order", None),
        "actionNumber": getattr(event, "event_num", None),
        "teamStartingPeriodWithBall": getattr(event, "team_starting_with_ball", None)
        if isinstance(event, StartOfPeriod)
        else None,
        "isPeriodStartEvent": isinstance(event, StartOfPeriod),
        "isPeriodEndEvent": isinstance(event, EndOfPeriod),
        "linkedShotActionNumber": rebound_linked_shot_action_number(event),
        "reboundOfMissedShotFlag": rebound_of_missed_shot_flag(event),
        "freeThrowTripSequenceNum": pbpstats_free_throw_trip_sequence(event),
        "freeThrowTripSize": getattr(event, "num_ft_for_trip", None) if isinstance(event, FreeThrow) else None,
    }


def ours_rows_for_game(s3_client: Any, game_id: str) -> list[dict[str, Any]]:
    payload = ours.read_json_payload(s3_client, f"{ours.SOURCE_PREFIX}game_id={game_id}.json")
    boxscore_context = ours.load_boxscore_context_for_game(s3_client, game_id)
    rows, _ = ours.build_rows_from_payload(payload, game_id, boxscore_context)
    return rows


def pbpstats_rows_for_game(game_id: str) -> list[dict[str, Any]]:
    teams = pbpstats_boxscore_teams(game_id)
    loader = ValidationEnhancedLoader(game_id, LiveEnhancedPbpWebLoader(), sorted(teams.keys()))
    return [pbpstats_event_row(event) for event in loader.items]


def field_is_comparable(field: str, ours_row: dict[str, Any], theirs_row: dict[str, Any]) -> bool:
    if field == "teamStartingPeriodWithBall":
        return bool(ours_row.get("isPeriodStartEvent") or theirs_row.get("isPeriodStartEvent"))
    if field in {"linkedShotActionNumber", "reboundOfMissedShotFlag"}:
        return bool(ours_row.get("isRebound") or theirs_row.get("linkedShotActionNumber") is not None or theirs_row.get("reboundOfMissedShotFlag"))
    if field == "freeThrowTripSequenceNum":
        descriptor = ours.normalized_action_type(ours_row.get("descriptor"))
        if (
            ours_row.get("freeThrowTripSize") == 1
            and descriptor in {"technical", "awayfromplay", "transitiontake", "take", "transition"}
        ):
            # pbpstats exposes trip size for these one-shot special free throws
            # but not a trip sequence position.
            return False
    if field in {"freeThrowTripSequenceNum", "freeThrowTripSize"}:
        return bool(ours_row.get("isFreeThrow") or theirs_row.get("freeThrowTripSequenceNum") is not None)
    return True


def compare_games(games: list[dict[str, str]], max_examples: int) -> dict[str, Any]:
    s3_client = boto3.client("s3")

    total_rows = 0
    compared_values = 0
    mismatch_count = 0
    mismatches_by_field: Counter[str] = Counter()
    mismatches_by_game: Counter[str] = Counter()
    mismatch_examples: list[dict[str, Any]] = []
    game_results: list[dict[str, Any]] = []

    for game in games:
        game_id = game["game_id"]
        ours_rows = ours_rows_for_game(s3_client, game_id)
        theirs_rows = pbpstats_rows_for_game(game_id)

        ours_map = {row_key(row): row for row in ours_rows}
        theirs_map = {row_key(row): row for row in theirs_rows}
        keys = sorted(set(ours_map) | set(theirs_map))
        total_rows += len(keys)

        game_mismatch_count = 0
        for key in keys:
            ours_row = ours_map.get(key)
            theirs_row = theirs_map.get(key)
            if ours_row is None or theirs_row is None:
                mismatch_count += 1
                game_mismatch_count += 1
                mismatches_by_field["__missing_event__"] += 1
                mismatches_by_game[game_id] += 1
                if len(mismatch_examples) < max_examples:
                    mismatch_examples.append(
                        {
                            "game_id": game_id,
                            "key": key,
                            "field": "__missing_event__",
                            "ours": None if ours_row is None else "present",
                            "pbpstats": None if theirs_row is None else "present",
                        }
                    )
                continue

            for field in PHASE6_FIELDS:
                if not field_is_comparable(field, ours_row, theirs_row):
                    continue
                compared_values += 1
                ours_value = ours_row.get(field)
                theirs_value = theirs_row.get(field)
                if ours_value == theirs_value:
                    continue

                mismatch_count += 1
                game_mismatch_count += 1
                mismatches_by_field[field] += 1
                mismatches_by_game[game_id] += 1
                if len(mismatch_examples) < max_examples:
                    mismatch_examples.append(
                        {
                            "game_id": game_id,
                            "key": key,
                            "field": field,
                            "ours": ours_value,
                            "pbpstats": theirs_value,
                            "actionType": ours_row.get("actionType"),
                            "subType": ours_row.get("subType"),
                            "description": ours_row.get("description"),
                        }
                    )

        game_results.append(
            {
                **game,
                "row_count": len(keys),
                "mismatch_count": game_mismatch_count,
            }
        )

    return {
        "games_checked": len(games),
        "rows_checked": total_rows,
        "values_compared": compared_values,
        "mismatch_count": mismatch_count,
        "field_mismatches": dict(mismatches_by_field.most_common()),
        "game_mismatches": dict(mismatches_by_game.most_common()),
        "game_results": game_results,
        "examples": mismatch_examples,
    }


def print_summary(summary: dict[str, Any]) -> None:
    print(f"Games checked: {summary['games_checked']}")
    print(f"Rows checked: {summary['rows_checked']}")
    print(f"Values compared: {summary['values_compared']}")
    print(f"Mismatches: {summary['mismatch_count']}")

    print("\nPer-game results:")
    for game in summary["game_results"]:
        print(
            "  "
            f"{game['game_id']} "
            f"{game['season_year']} {game['season_type']} "
            f"{game['away_team_abbreviation']}@{game['home_team_abbreviation']} "
            f"rows={game['row_count']} mismatches={game['mismatch_count']}"
        )

    print("\nMismatch counts by field:")
    if summary["field_mismatches"]:
        for field, count in summary["field_mismatches"].items():
            print(f"  {field}: {count}")
    else:
        print("  none")

    print("\nMismatch examples:")
    if summary["examples"]:
        for example in summary["examples"]:
            print(
                "  "
                f"{example['game_id']} {example['key']} {example['field']} "
                f"ours={example['ours']} pbpstats={example['pbpstats']} "
                f"actionType={example.get('actionType')} subType={example.get('subType')}"
            )
    else:
        print("  none")


def main() -> int:
    args = parse_args()
    games = load_validation_games(args.game_set_csv, args.game_ids, args.limit)
    summary = compare_games(games, args.max_examples)

    print_summary(summary)

    if args.json_output is not None:
        args.json_output.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nJSON summary written to {args.json_output}")

    return 1 if summary["mismatch_count"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
