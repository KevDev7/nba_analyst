#!/usr/bin/env python3
"""
Run Phase 5 possession lineup stamping validation against pbpstats event lineup context.
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
PBPSTATS_DIR = REPO_ROOT / "reference" / "pbpstats"
TESTS_DIR = REPO_ROOT / "pipelines" / "athena" / "tests" / "silver"

import sys

for path in (SILVER_TRANSFORM_DIR, PBPSTATS_DIR, TESTS_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import build_silver_possessions as ours
from pbpstats.data_loader.live.enhanced_pbp.loader import LiveEnhancedPbpLoader
from pbpstats.data_loader.live.enhanced_pbp.web import LiveEnhancedPbpWebLoader
from pbpstats.resources.possessions.possession import Possession
from run_playbyplay_phase_1_3_parity import pbpstats_boxscore_teams


DEFAULT_GAME_SET_CSV = (
    REPO_ROOT / "pipelines" / "athena" / "metadata" / "playbyplay_phase_1_3_expanded_validation_games.csv"
)


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


def period_starters_from_on_court_rows(on_court_rows: list[dict[str, Any]]) -> dict[int, dict[int, list[int]]]:
    starters_by_period: dict[int, dict[int, list[int]]] = {}
    if not on_court_rows:
        return starters_by_period

    sorted_rows = sorted(
        on_court_rows,
        key=lambda row: (
            ours.pbp_silver.to_int_or_none(row.get("period")) or 0,
            ours.pbp_silver.to_int_or_none(row.get("start_orderNumber")) or 0,
            ours.pbp_silver.to_int_or_none(row.get("stint_id")) or 0,
        ),
    )

    for row in sorted_rows:
        period = ours.pbp_silver.to_int_or_none(row.get("period"))
        if period is None or period in starters_by_period:
            continue
        home_team_id = ours.pbp_silver.to_int_or_none(row.get("home_teamId"))
        away_team_id = ours.pbp_silver.to_int_or_none(row.get("away_teamId"))
        if home_team_id is None or away_team_id is None:
            continue
        home_person_ids = [
            player_id
            for player_id in (ours.pbp_silver.to_int_or_none(value) for value in row.get("home_personIds") or [])
            if player_id is not None
        ]
        away_person_ids = [
            player_id
            for player_id in (ours.pbp_silver.to_int_or_none(value) for value in row.get("away_personIds") or [])
            if player_id is not None
        ]
        starters_by_period[period] = {
            home_team_id: home_person_ids,
            away_team_id: away_person_ids,
        }

    return starters_by_period


class LineupValidationEnhancedLoader(LiveEnhancedPbpLoader):
    def __init__(
        self,
        game_id: str,
        source_loader: LiveEnhancedPbpWebLoader,
        starters_by_period: dict[int, dict[int, list[int]]],
    ):
        self._starters_by_period = starters_by_period
        super().__init__(game_id, source_loader)

    def _set_period_start_items(self) -> None:
        for index in self.start_period_indices:
            event = self.items[index]
            event.team_starting_with_ball = event.get_team_starting_with_ball()
            period = getattr(event, "period", None)
            event.period_starters = self._starters_by_period.get(period, {})


def row_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return row.get("period"), row.get("possessionNumberInPeriod")


def normalized_lineup_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def lineup_id_player_count(value: Any) -> int:
    lineup_id = normalized_lineup_id(value)
    if lineup_id is None:
        return 0
    return len([part for part in lineup_id.split("-") if part])


def periods_with_pre_start_substitutions(pbp_rows: list[dict[str, Any]]) -> set[int]:
    periods: set[int] = set()
    rows_by_period: dict[int, list[dict[str, Any]]] = {}
    for row in pbp_rows:
        period = ours.pbp_silver.to_int_or_none(row.get("period"))
        if period is None:
            continue
        rows_by_period.setdefault(period, []).append(row)

    for period, rows in rows_by_period.items():
        ordered_rows = sorted(
            rows,
            key=lambda row: (
                ours.pbp_silver.to_int_or_none(row.get("orderNumber")) or 0,
                ours.pbp_silver.to_int_or_none(row.get("actionNumber")) or 0,
            ),
        )
        for row in ordered_rows:
            action_type = str(row.get("actionType") or "").lower()
            sub_type = str(row.get("subType") or "").lower()
            if action_type == "period" and sub_type == "start":
                break
            if action_type == "substitution":
                periods.add(period)
                break

    return periods


def pbpstats_possession_lineup_row(possession: Any, teams: dict[int, dict[str, Any]]) -> dict[str, Any]:
    home_team_id = next((team_id for team_id, meta in teams.items() if meta.get("location") == "h"), None)
    away_team_id = next((team_id for team_id, meta in teams.items() if meta.get("location") == "v"), None)

    home_lineup_ids: set[str] = set()
    away_lineup_ids: set[str] = set()
    missing_lineup_context = False

    for event in possession.events:
        if getattr(event, "action_type", None) == "substitution":
            continue
        try:
            lineup_ids = getattr(event, "lineup_ids", None)
        except Exception:
            missing_lineup_context = True
            continue
        if not isinstance(lineup_ids, dict):
            missing_lineup_context = True
            continue

        home_lineup_id = normalized_lineup_id(lineup_ids.get(home_team_id))
        away_lineup_id = normalized_lineup_id(lineup_ids.get(away_team_id))
        if home_lineup_id is None or away_lineup_id is None:
            missing_lineup_context = True
            continue
        home_lineup_ids.add(home_lineup_id)
        away_lineup_ids.add(away_lineup_id)

    issues: list[str] = []
    if not home_lineup_ids or not away_lineup_ids:
        issues.append("missing_pbpstats_lineup_context")
    elif missing_lineup_context:
        issues.append("partial_pbpstats_lineup_context")
    if len(home_lineup_ids) > 1:
        issues.append(f"multiple_home_lineups(count={len(home_lineup_ids)})")
    if len(away_lineup_ids) > 1:
        issues.append(f"multiple_away_lineups(count={len(away_lineup_ids)})")

    home_lineup_id = next(iter(home_lineup_ids)) if len(home_lineup_ids) == 1 else None
    away_lineup_id = next(iter(away_lineup_ids)) if len(away_lineup_ids) == 1 else None
    home_lineup_size = lineup_id_player_count(home_lineup_id)
    away_lineup_size = lineup_id_player_count(away_lineup_id)
    if home_lineup_id is not None and home_lineup_size != 5:
        issues.append(f"invalid_home_lineup_size(count={home_lineup_size})")
    if away_lineup_id is not None and away_lineup_size != 5:
        issues.append(f"invalid_away_lineup_size(count={away_lineup_size})")

    return {
        "period": getattr(possession, "period", None),
        "possessionNumberInPeriod": getattr(possession, "number", None),
        "homeLineupId": home_lineup_id,
        "awayLineupId": away_lineup_id,
        "lineupValidFlag": int(len(issues) == 0),
        "lineupIssue": " | ".join(issues) if issues else None,
    }


def ours_rows_for_game(s3_client: Any, game_id: str) -> list[dict[str, Any]]:
    pbp_rows = ours.read_playbyplay_rows_from_s3(s3_client, f"{ours.SOURCE_PREFIX}game_id={game_id}.parquet")
    on_court_rows = ours.read_on_court_rows_from_s3(s3_client, game_id)
    return ours.build_possession_rows_from_events(pbp_rows, on_court_rows=on_court_rows)


def load_validated_pbpstats_possessions_with_on_court(
    game_id: str,
    on_court_rows: list[dict[str, Any]],
) -> list[Possession]:
    starters_by_period = period_starters_from_on_court_rows(on_court_rows)
    loader = LineupValidationEnhancedLoader(game_id, LiveEnhancedPbpWebLoader(), starters_by_period)

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
        period_start = any(getattr(event, "action_type", None) == "period" and getattr(event, "sub_type", None) == "start" for event in possession.events)
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


def pbpstats_rows_for_game(game_id: str, on_court_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    teams = pbpstats_boxscore_teams(game_id)
    possessions = load_validated_pbpstats_possessions_with_on_court(game_id, on_court_rows)
    return [pbpstats_possession_lineup_row(possession, teams) for possession in possessions]


def compare_games(games: list[dict[str, str]], max_examples: int) -> dict[str, Any]:
    s3_client = boto3.client("s3")

    total_rows = 0
    mismatch_count = 0
    compared_values = 0
    ignored_rows = 0
    mismatches_by_field: Counter[str] = Counter()
    mismatches_by_game: Counter[str] = Counter()
    ignored_by_reason: Counter[str] = Counter()
    mismatch_examples: list[dict[str, Any]] = []
    game_results: list[dict[str, Any]] = []

    for game in games:
        game_id = game["game_id"]
        on_court_rows = ours.read_on_court_rows_from_s3(s3_client, game_id)
        pbp_rows = ours.read_playbyplay_rows_from_s3(
            s3_client, f"{ours.SOURCE_PREFIX}game_id={game_id}.parquet"
        )
        unreliable_periods = periods_with_pre_start_substitutions(pbp_rows)
        ours_rows = ours.build_possession_rows_from_events(pbp_rows, on_court_rows=on_court_rows)
        theirs_rows = pbpstats_rows_for_game(game_id, on_court_rows)

        ours_map = {row_key(row): row for row in ours_rows}
        theirs_map = {row_key(row): row for row in theirs_rows}
        keys = sorted(set(ours_map) | set(theirs_map))
        total_rows += len(keys)

        game_mismatch_count = 0
        game_ignored_count = 0
        for key in keys:
            ours_row = ours_map.get(key)
            theirs_row = theirs_map.get(key)
            if ours_row is None or theirs_row is None:
                mismatch_count += 1
                game_mismatch_count += 1
                mismatches_by_field["__missing_possession__"] += 1
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

            period = ours.pbp_silver.to_int_or_none(ours_row.get("period"))
            if period in unreliable_periods:
                ignored_rows += 1
                game_ignored_count += 1
                ignored_by_reason["period_has_pre_start_substitutions"] += 1
                continue

            pbpstats_issue = str(theirs_row.get("lineupIssue") or "")
            if "invalid_home_lineup_size" in pbpstats_issue or "invalid_away_lineup_size" in pbpstats_issue:
                ignored_rows += 1
                game_ignored_count += 1
                ignored_by_reason["pbpstats_invalid_lineup_size"] += 1
                continue

            if "partial_pbpstats_lineup_context" in pbpstats_issue:
                ignored_rows += 1
                game_ignored_count += 1
                ignored_by_reason["pbpstats_partial_lineup_context"] += 1
                continue

            if "missing_pbpstats_lineup_context" in pbpstats_issue:
                ignored_rows += 1
                game_ignored_count += 1
                ignored_by_reason["pbpstats_missing_lineup_context"] += 1
                continue

            fields_to_compare = ["lineupValidFlag"]
            if int(ours_row.get("lineupValidFlag") or 0) == 1 or int(theirs_row.get("lineupValidFlag") or 0) == 1:
                fields_to_compare.extend(["homeLineupId", "awayLineupId"])

            for field in fields_to_compare:
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
                            "ours_issue": ours_row.get("lineupIssue"),
                            "pbpstats_issue": theirs_row.get("lineupIssue"),
                            "startActionNumber": ours_row.get("startActionNumber"),
                            "endActionNumber": ours_row.get("endActionNumber"),
                        }
                    )

            if int(ours_row.get("lineupValidFlag") or 0) == 0:
                compared_values += 1
                if not ours_row.get("lineupIssue"):
                    mismatch_count += 1
                    game_mismatch_count += 1
                    mismatches_by_field["missing_lineupIssue"] += 1
                    mismatches_by_game[game_id] += 1
                    if len(mismatch_examples) < max_examples:
                        mismatch_examples.append(
                            {
                                "game_id": game_id,
                                "key": key,
                                "field": "missing_lineupIssue",
                                "ours": ours_row.get("lineupIssue"),
                                "pbpstats": theirs_row.get("lineupIssue"),
                            }
                        )

        game_results.append(
            {
                **game,
                "row_count": len(keys),
                "mismatch_count": game_mismatch_count,
                "ignored_count": game_ignored_count,
            }
        )

    return {
        "games_checked": len(games),
        "rows_checked": total_rows,
        "values_compared": compared_values,
        "mismatch_count": mismatch_count,
        "ignored_rows": ignored_rows,
        "ignored_by_reason": dict(ignored_by_reason.most_common()),
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
    print(f"Ignored rows: {summary['ignored_rows']}")

    print("\nPer-game results:")
    for game in summary["game_results"]:
        print(
            "  "
            f"{game['game_id']} "
            f"{game['season_year']} {game['season_type']} "
            f"{game['away_team_abbreviation']}@{game['home_team_abbreviation']} "
            f"rows={game['row_count']} mismatches={game['mismatch_count']} ignored={game['ignored_count']}"
        )

    print("\nIgnored rows by reason:")
    if summary["ignored_by_reason"]:
        for reason, count in summary["ignored_by_reason"].items():
            print(f"  {reason}: {count}")
    else:
        print("  none")

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
    summary = compare_games(games, args.max_examples)

    print_summary(summary)

    if args.json_output is not None:
        args.json_output.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nJSON summary written to {args.json_output}")

    return 1 if summary["mismatch_count"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
