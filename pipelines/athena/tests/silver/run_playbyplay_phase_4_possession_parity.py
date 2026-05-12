#!/usr/bin/env python3
"""
Run expanded Phase 4 possession parity validation against pbpstats.
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

import sys

if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))
if PBPSTATS_DIR.exists() and str(PBPSTATS_DIR) not in sys.path:
    sys.path.insert(0, str(PBPSTATS_DIR))

import build_silver_possessions as ours
from run_playbyplay_phase_1_3_parity import ValidationEnhancedLoader, pbpstats_boxscore_teams
from pbpstats.data_loader.live.enhanced_pbp.web import LiveEnhancedPbpWebLoader
from pbpstats.resources.enhanced_pbp import (
    FieldGoal,
    FreeThrow,
    JumpBall,
    Rebound,
    StartOfPeriod,
    Substitution,
    Timeout,
    Turnover,
)
from pbpstats.resources.possessions.possession import Possession


DEFAULT_GAME_SET_CSV = (
    REPO_ROOT / "pipelines" / "athena" / "metadata" / "playbyplay_phase_1_3_expanded_validation_games.csv"
)

PARITY_FIELDS = [
    "period",
    "possessionNumberInPeriod",
    "startClock",
    "endClock",
    "offenseTeamId",
    "defenseTeamId",
    "offenseHomeAway",
    "defenseHomeAway",
    "startScoreMargin",
    "endScoreMargin",
    "pointsScoredOnPossession",
    "possessionHasTimeout",
    "previousPossessionHasTimeout",
    "possessionStartType",
    "possessionEndType",
    "countsAsPossession",
    "isSecondChancePossession",
    "isPenaltyPossession",
    "fieldGoalAttempts",
    "freeThrowAttempts",
    "turnovers",
    "offensiveRebounds",
    "madeFieldGoals",
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


def load_validation_games(csv_path: Path, explicit_game_ids: list[str], limit: int | None) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as infile:
        rows = list(csv.DictReader(infile))

    if explicit_game_ids:
        explicit_set = set(explicit_game_ids)
        rows = [row for row in rows if row["game_id"] in explicit_set]
        missing_ids = [game_id for game_id in explicit_game_ids if game_id not in {row["game_id"] for row in rows}]
        if missing_ids:
            raise SystemExit(f"Game ids not found in {csv_path}: {', '.join(missing_ids)}")

    if limit is not None:
        rows = rows[:limit]

    return rows


def load_validated_pbpstats_possessions(game_id: str) -> list[Possession]:
    teams = pbpstats_boxscore_teams(game_id)
    loader = ValidationEnhancedLoader(game_id, LiveEnhancedPbpWebLoader(), sorted(teams.keys()))

    grouped_events: list[list[Any]] = []
    current_events: list[Any] = []
    for event in loader.items:
        current_events.append(event)
        if event.is_possession_ending_event:
            grouped_events.append(current_events)
            current_events = []

    items = [Possession(events) for events in grouped_events]
    number = 1
    for index, possession in enumerate(items):
        period_start = any(isinstance(event, StartOfPeriod) for event in possession.events)
        if index == 0 and index == len(items) - 1:
            possession.previous_possession = None
            possession.next_possession = None
        elif period_start or index == 0:
            possession.previous_possession = None
            possession.next_possession = items[index + 1]
            number = 1
        elif index == len(items) - 1 or possession.period != items[index + 1].period:
            possession.previous_possession = items[index - 1]
            possession.next_possession = None
        else:
            possession.previous_possession = items[index - 1]
            possession.next_possession = items[index + 1]
        possession.number = number
        number += 1
    return items


def other_team_id(team_id: int | None, teams: dict[int, dict[str, Any]]) -> int | None:
    if team_id is None:
        return None
    for candidate in teams:
        if candidate != team_id:
            return candidate
    return None


def last_non_substitution_event(events: list[Any]) -> Any:
    for event in reversed(events):
        if not isinstance(event, Substitution):
            return event
    return events[-1]


def possession_ending_event(events: list[Any]) -> Any:
    for event in reversed(events):
        if bool(getattr(event, "is_possession_ending_event", False)):
            return event
    return last_non_substitution_event(events)


def normalize_pbpstats_start_type(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    mappings = {
        "OffDeadball": "off_deadball",
        "OffTimeout": "off_timeout",
        "OffFTMake": "off_ft_make",
        "OffFTMiss": "off_ft_miss",
        "OffLiveBallTurnover": "off_live_ball_turnover",
        "OffArc3Make": "off_3pt_make",
        "OffCorner3Make": "off_3pt_make",
        "OffArc3Miss": "off_3pt_miss",
        "OffCorner3Miss": "off_3pt_miss",
        "OffArc3Block": "off_3pt_block",
        "OffCorner3Block": "off_3pt_block",
        "OffAtRimMake": "off_2pt_make",
        "OffShortMidRangeMake": "off_2pt_make",
        "OffLongMidRangeMake": "off_2pt_make",
        "OffUnknownDistance2ptMake": "off_2pt_make",
        "OffAtRimMiss": "off_2pt_miss",
        "OffShortMidRangeMiss": "off_2pt_miss",
        "OffLongMidRangeMiss": "off_2pt_miss",
        "OffUnknownDistance2ptMiss": "off_2pt_miss",
        "OffAtRimBlock": "off_2pt_block",
        "OffShortMidRangeBlock": "off_2pt_block",
        "OffLongMidRangeBlock": "off_2pt_block",
        "OffUnknownDistance2ptBlock": "off_2pt_block",
    }
    return mappings.get(text, text)


def pbpstats_end_type(possession: Possession) -> str | None:
    for candidate in reversed(possession.events):
        if getattr(candidate, "action_type", None) == "period" and getattr(candidate, "sub_type", None) == "end":
            return "period_end"
    event = possession_ending_event(possession.events)
    action_type = getattr(event, "action_type", None)
    sub_type = getattr(event, "sub_type", None)
    if isinstance(event, FieldGoal) and bool(getattr(event, "is_made", False)):
        return "made_shot"
    if isinstance(event, Turnover):
        return "turnover"
    if isinstance(event, Rebound):
        if getattr(event, "oreb", False):
            return "rebound"
        return "def_rebound"
    if isinstance(event, FreeThrow):
        return "free_throw"
    if isinstance(event, JumpBall):
        return "jump_ball_change"
    if (action_type == "period" and sub_type == "end") or action_type == "game":
        return "period_end"
    if isinstance(event, Timeout):
        return "offense_change"
    return "offense_change"


def pbpstats_points_scored_on_possession(possession: Possession) -> int | None:
    if possession.previous_possession is None:
        start_score = possession.events[0].score
    else:
        start_score = possession.previous_possession.events[-1].score
    end_score = possession.events[-1].score
    offense_team_id = possession.offense_team_id
    return int(end_score.get(offense_team_id, 0)) - int(start_score.get(offense_team_id, 0))


def score_margin_from_score_dict(
    offense_team_id: int | None,
    score: dict[Any, Any],
) -> int | None:
    if offense_team_id is None:
        return None
    offense_points = int(score.get(offense_team_id, 0))
    defense_points = None
    for team_id, points in score.items():
        if team_id != offense_team_id:
            defense_points = points
            break
    return offense_points - int(defense_points or 0)


def pbpstats_possession_row(possession: Possession, teams: dict[int, dict[str, Any]]) -> dict[str, Any]:
    offense_team_id = possession.offense_team_id
    defense_team_id = other_team_id(offense_team_id, teams)
    end_event = possession_ending_event(possession.events)
    end_score = possession.events[-1].score

    return {
        "period": possession.period,
        "possessionNumberInPeriod": possession.number,
        "startClock": possession.start_time,
        "endClock": possession.end_time,
        "offenseTeamId": offense_team_id,
        "defenseTeamId": defense_team_id,
        "offenseHomeAway": None if offense_team_id is None else teams.get(offense_team_id, {}).get("location"),
        "defenseHomeAway": None if defense_team_id is None else teams.get(defense_team_id, {}).get("location"),
        "startScoreMargin": possession.start_score_margin,
        "endScoreMargin": score_margin_from_score_dict(
            offense_team_id,
            end_score,
        ),
        "possessionHasTimeout": possession.possession_has_timeout,
        "previousPossessionHasTimeout": possession.previous_possession_has_timeout,
        "possessionStartType": normalize_pbpstats_start_type(possession.possession_start_type),
        "possessionEndType": pbpstats_end_type(possession),
        "pointsScoredOnPossession": pbpstats_points_scored_on_possession(possession),
        "countsAsPossession": bool(getattr(end_event, "count_as_possession", False)),
        "isSecondChancePossession": any(
            bool(event.is_second_chance_event())
            for event in possession.events
        ),
        "isPenaltyPossession": any(
            bool(event.is_penalty_event())
            for event in possession.events
            if getattr(event, "action_type", None) != "game"
        ),
        "fieldGoalAttempts": sum(
            1 for event in possession.events if isinstance(event, FieldGoal)
        ),
        "freeThrowAttempts": sum(
            1 for event in possession.events if isinstance(event, FreeThrow)
        ),
        "turnovers": sum(
            1 for event in possession.events if isinstance(event, Turnover)
        ),
        "offensiveRebounds": sum(
            1
            for event in possession.events
            if isinstance(event, Rebound)
            and bool(getattr(event, "oreb", False))
            and bool(getattr(event, "is_real_rebound", False))
        ),
        "madeFieldGoals": sum(
            1
            for event in possession.events
            if isinstance(event, FieldGoal) and bool(getattr(event, "is_made", False))
        ),
    }


def ours_rows_for_game(s3_client: Any, game_id: str) -> list[dict[str, Any]]:
    key = f"{ours.SOURCE_PREFIX}game_id={game_id}.parquet"
    playbyplay_rows = ours.read_playbyplay_rows_from_s3(s3_client, key)
    return ours.build_possession_rows_from_events(playbyplay_rows)


def pbpstats_rows_for_game(game_id: str) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    teams = pbpstats_boxscore_teams(game_id)
    possessions = load_validated_pbpstats_possessions(game_id)
    rows = [pbpstats_possession_row(possession, teams) for possession in possessions]
    return rows, teams


def row_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return row.get("period"), row.get("possessionNumberInPeriod")


def compare_games(games: list[dict[str, str]], fields: list[str], max_examples: int) -> dict[str, Any]:
    s3_client = boto3.client("s3")

    total_rows = 0
    compared_values = 0
    mismatch_count = 0
    game_results: list[dict[str, Any]] = []
    mismatches_by_field: Counter[str] = Counter()
    mismatches_by_game: Counter[str] = Counter()
    mismatch_examples: list[dict[str, Any]] = []

    for game in games:
        game_id = game["game_id"]
        ours_rows = ours_rows_for_game(s3_client, game_id)
        theirs_rows, _ = pbpstats_rows_for_game(game_id)

        ours_map = {row_key(row): row for row in ours_rows}
        theirs_map = {row_key(row): row for row in theirs_rows}
        keys = sorted(set(ours_map) | set(theirs_map))

        game_mismatch_count = 0
        missing_keys: list[tuple[Any, Any]] = []
        total_rows += len(keys)

        for key in keys:
            ours_row = ours_map.get(key)
            theirs_row = theirs_map.get(key)
            if ours_row is None or theirs_row is None:
                missing_keys.append(key)
                mismatch_count += 1
                game_mismatch_count += 1
                mismatches_by_game[game_id] += 1
                if len(mismatch_examples) < max_examples:
                    mismatch_examples.append(
                        {
                            "game_id": game_id,
                            "key": key,
                            "field": "__missing_possession__",
                            "ours": None if ours_row is None else "present",
                            "pbpstats": None if theirs_row is None else "present",
                        }
                    )
                continue

            for field in fields:
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
                            "startActionNumber": ours_row.get("startActionNumber"),
                            "endActionNumber": ours_row.get("endActionNumber"),
                        }
                    )

        game_results.append(
            {
                **game,
                "row_count": len(keys),
                "missing_key_count": len(missing_keys),
                "mismatch_count": game_mismatch_count,
                "missing_keys": missing_keys[:10],
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
                f"ours={example['ours']} pbpstats={example['pbpstats']}"
            )
    else:
        print("  none")


def main() -> int:
    args = parse_args()
    games = load_validation_games(args.game_set_csv, args.game_ids, args.limit)
    summary = compare_games(games, PARITY_FIELDS, args.max_examples)

    print_summary(summary)

    if args.json_output is not None:
        args.json_output.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nJSON summary written to {args.json_output}")

    return 1 if summary["mismatch_count"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
