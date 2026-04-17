#!/usr/bin/env python3
"""
Run expanded Phase 1-3 play-by-play parity validation against pbpstats.

Example:
  python pipelines/athena/tests/silver/run_playbyplay_phase_1_3_parity.py
  python pipelines/athena/tests/silver/run_playbyplay_phase_1_3_parity.py --limit 10
  python pipelines/athena/tests/silver/run_playbyplay_phase_1_3_parity.py --phase 3
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import boto3


REPO_ROOT = Path(__file__).resolve().parents[3]
SILVER_TRANSFORM_DIR = REPO_ROOT / "pipelines" / "athena" / "transform" / "silver"
PBPSTATS_DIR = REPO_ROOT / "reference" / "pbpstats"

import sys

if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))
if str(PBPSTATS_DIR) not in sys.path:
    sys.path.insert(0, str(PBPSTATS_DIR))

import build_silver_playbyplay_events as ours
from pbpstats.data_loader.live.boxscore.web import LiveBoxscoreWebLoader
from pbpstats.data_loader.live.enhanced_pbp.loader import LiveEnhancedPbpLoader
from pbpstats.data_loader.live.enhanced_pbp.web import LiveEnhancedPbpWebLoader
from pbpstats.resources.enhanced_pbp import (
    FieldGoal,
    Foul,
    FreeThrow,
    JumpBall,
    Rebound,
    StartOfPeriod,
    Substitution,
    Timeout,
    Turnover,
)


DEFAULT_GAME_SET_CSV = (
    REPO_ROOT / "pipelines" / "athena" / "metadata" / "playbyplay_phase_1_3_expanded_validation_games.csv"
)

PHASE_FIELDS = {
    "1": [
        "prevActionNumber",
        "nextActionNumber",
        "prevOrderNumber",
        "nextOrderNumber",
        "secondsRemainingInPeriod",
        "secondsSincePreviousEvent",
        "isMadeShot",
        "isMissedShot",
        "isFreeThrow",
        "isRebound",
        "isTurnover",
        "isFoul",
        "isSubstitution",
        "isTimeout",
        "isJumpBall",
    ],
    "2": [
        "resolvedOffenseTeamId",
        "resolvedDefenseTeamId",
        "offenseHomeAway",
        "defenseHomeAway",
        "scoreMarginBefore",
        "scoreMarginAfter",
        "isPossessionEndingEvent",
        "countAsPossession",
    ],
    "3": [
        "foulsToGiveOffense",
        "foulsToGiveDefense",
        "isSecondChanceEvent",
        "isPenaltyEvent",
        "isOreb",
        "isDreb",
        "isPlaceholderRebound",
        "isShootingFoul",
        "isTechnicalFt",
        "isFlagrantFt",
        "isBadPassTurnover",
        "isLostBallTurnover",
        "isTravelTurnover",
        "isShotClockTurnover",
    ],
}

KNOWN_PBPSTATS_TERMINAL_BUG_FIELDS = {
    "resolvedOffenseTeamId",
    "resolvedDefenseTeamId",
    "offenseHomeAway",
    "defenseHomeAway",
    "scoreMarginBefore",
    "scoreMarginAfter",
    "foulsToGiveOffense",
    "foulsToGiveDefense",
    "isPenaltyEvent",
}


class ValidationEnhancedLoader(LiveEnhancedPbpLoader):
    """Skip starter repair while preserving enough context for parity checks."""

    def __init__(self, game_id: str, source_loader: LiveEnhancedPbpWebLoader, team_ids: list[int]):
        self._validation_team_ids = team_ids
        super().__init__(game_id, source_loader)

    def _set_period_start_items(self) -> None:
        for index in self.start_period_indices:
            self.items[index].team_starting_with_ball = self.items[index].get_team_starting_with_ball()
            self.items[index].period_starters = {
                team_id: []
                for team_id in self._validation_team_ids
            }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game-set-csv",
        type=Path,
        default=DEFAULT_GAME_SET_CSV,
        help="CSV of validation game_ids.",
    )
    parser.add_argument(
        "--phase",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Limit comparison to one phase or run all phases.",
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


def selected_fields(phase: str) -> list[str]:
    if phase == "all":
        fields: list[str] = []
        for phase_key in ("1", "2", "3"):
            fields.extend(PHASE_FIELDS[phase_key])
        return fields
    return list(PHASE_FIELDS[phase])


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


def other_team_id(team_id: int | None, teams: dict[int, dict[str, Any]]) -> int | None:
    if team_id is None:
        return None
    for candidate in teams:
        if candidate != team_id:
            return candidate
    return None


def default_lookup(mapping: Any, key: int | None) -> int | None:
    if key is None:
        return None
    try:
        return mapping[key]
    except Exception:
        return None


def pbpstats_boxscore_teams(game_id: str) -> dict[int, dict[str, Any]]:
    loader = LiveBoxscoreWebLoader()
    boxscore = loader.load_data(game_id)
    teams: dict[int, dict[str, Any]] = {}
    for team_key, location in (("homeTeam", "h"), ("awayTeam", "v")):
        team = (boxscore.get("game") or {}).get(team_key) or {}
        team_id = team.get("teamId")
        if team_id is not None:
            teams[int(team_id)] = {"location": location}
    return teams


def same_period_event_neighbor(event: Any, direction: str) -> Any | None:
    neighbor = getattr(event, direction, None)
    if neighbor is None or getattr(neighbor, "period", None) != getattr(event, "period", None):
        return None
    return neighbor


def pbpstats_event_row(event: Any, teams: dict[int, dict[str, Any]]) -> dict[str, Any]:
    previous_event = same_period_event_neighbor(event, "previous_event")
    next_event = same_period_event_neighbor(event, "next_event")

    offense_team_id = event.get_offense_team_id()
    if offense_team_id in (0, "0"):
        offense_team_id = None
    defense_team_id = other_team_id(offense_team_id, teams)

    fouls_to_give = getattr(event, "fouls_to_give", {})

    return {
        "prevActionNumber": None if previous_event is None else getattr(previous_event, "event_num", None),
        "nextActionNumber": None if next_event is None else getattr(next_event, "event_num", None),
        "prevOrderNumber": None if previous_event is None else getattr(previous_event, "order", None),
        "nextOrderNumber": None if next_event is None else getattr(next_event, "order", None),
        "secondsRemainingInPeriod": getattr(event, "seconds_remaining", None),
        "secondsSincePreviousEvent": getattr(event, "seconds_since_previous_event", None),
        "isMadeShot": isinstance(event, FieldGoal) and bool(getattr(event, "is_made", False)),
        "isMissedShot": isinstance(event, FieldGoal) and not bool(getattr(event, "is_made", False)),
        "isFreeThrow": isinstance(event, FreeThrow),
        "isRebound": isinstance(event, Rebound),
        "isTurnover": isinstance(event, Turnover),
        "isFoul": isinstance(event, Foul),
        "isSubstitution": isinstance(event, Substitution),
        "isTimeout": isinstance(event, Timeout),
        "isJumpBall": isinstance(event, JumpBall),
        "resolvedOffenseTeamId": offense_team_id,
        "resolvedDefenseTeamId": defense_team_id,
        "offenseHomeAway": None if offense_team_id is None else teams.get(offense_team_id, {}).get("location"),
        "defenseHomeAway": None if defense_team_id is None else teams.get(defense_team_id, {}).get("location"),
        "scoreMarginBefore": getattr(event, "score_margin", None),
        "scoreMarginAfter": ours.score_margin_from_offense_team(
            offense_team_id,
            getattr(event, "home_score", None),
            getattr(event, "away_score", None),
            teams,
        ),
        "isPossessionEndingEvent": bool(getattr(event, "is_possession_ending_event", False)),
        "countAsPossession": bool(getattr(event, "count_as_possession", False)),
        "foulsToGiveOffense": default_lookup(fouls_to_give, offense_team_id),
        "foulsToGiveDefense": default_lookup(fouls_to_give, defense_team_id),
        "isSecondChanceEvent": bool(event.is_second_chance_event()),
        "isPenaltyEvent": bool(event.is_penalty_event()),
        "isOreb": bool(getattr(event, "oreb", False)),
        "isDreb": bool(hasattr(event, "oreb") and not getattr(event, "oreb", False)),
        "isPlaceholderRebound": bool(getattr(event, "is_placeholder", False)),
        "isShootingFoul": bool(getattr(event, "is_shooting_foul", False)),
        "isTechnicalFt": bool(getattr(event, "is_technical_ft", False)),
        "isFlagrantFt": bool(getattr(event, "is_flagrant_ft", False)),
        "isBadPassTurnover": bool(getattr(event, "is_bad_pass", False)),
        "isLostBallTurnover": bool(getattr(event, "is_lost_ball", False)),
        "isTravelTurnover": bool(getattr(event, "is_travel", False)),
        "isShotClockTurnover": bool(getattr(event, "is_shot_clock_violation", False)),
    }


def ours_rows_for_game(s3_client: Any, game_id: str) -> list[dict[str, Any]]:
    payload = ours.read_json_payload(s3_client, f"{ours.SOURCE_PREFIX}game_id={game_id}.json")
    boxscore_context = ours.load_boxscore_context_for_game(s3_client, game_id)
    rows, _ = ours.build_rows_from_payload(payload, game_id, boxscore_context)
    return rows


def pbpstats_rows_for_game(game_id: str) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    teams = pbpstats_boxscore_teams(game_id)
    loader = ValidationEnhancedLoader(game_id, LiveEnhancedPbpWebLoader(), sorted(teams.keys()))
    rows: list[dict[str, Any]] = []
    for event in loader.items:
        row = pbpstats_event_row(event, teams)
        row["period"] = getattr(event, "period", None)
        row["orderNumber"] = getattr(event, "order", None)
        row["actionNumber"] = getattr(event, "event_num", None)
        rows.append(row)
    return rows, teams


def row_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return row.get("period"), row.get("orderNumber"), row.get("actionNumber")


def is_known_terminal_bug(row: dict[str, Any], field: str) -> bool:
    return (
        field in KNOWN_PBPSTATS_TERMINAL_BUG_FIELDS
        and ours.normalized_action_type(row.get("actionType")) == "game"
        and ours.normalized_action_type(row.get("subType")) == "end"
    )


def is_known_replay_clock_bug(row: dict[str, Any], field: str, ours_value: Any, theirs_value: Any) -> bool:
    return (
        field == "secondsSincePreviousEvent"
        and ours.normalized_action_type(row.get("actionType")) == "instantreplay"
        and isinstance(ours_value, (int, float))
        and isinstance(theirs_value, (int, float))
        and ours_value == 0
        and theirs_value < 0
    )


def compare_games(
    games: list[dict[str, str]],
    fields: list[str],
    max_examples: int,
) -> dict[str, Any]:
    s3_client = boto3.client("s3")

    total_rows = 0
    compared_values = 0
    mismatch_count = 0
    ignored_mismatch_count = 0
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
        game_ignored_count = 0
        missing_keys: list[tuple[Any, Any, Any]] = []
        total_rows += len(keys)

        for key in keys:
            ours_row = ours_map.get(key)
            theirs_row = theirs_map.get(key)
            if ours_row is None or theirs_row is None:
                missing_keys.append(key)
                continue

            for field in fields:
                compared_values += 1
                ours_value = ours_row.get(field)
                theirs_value = theirs_row.get(field)
                if ours_value == theirs_value:
                    continue

                if is_known_terminal_bug(ours_row, field) or is_known_replay_clock_bug(
                    ours_row, field, ours_value, theirs_value
                ):
                    ignored_mismatch_count += 1
                    game_ignored_count += 1
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
                "missing_key_count": len(missing_keys),
                "mismatch_count": game_mismatch_count,
                "ignored_known_bug_count": game_ignored_count,
                "missing_keys": missing_keys[:10],
            }
        )

    return {
        "games_checked": len(games),
        "rows_checked": total_rows,
        "values_compared": compared_values,
        "mismatch_count": mismatch_count,
        "ignored_known_bug_count": ignored_mismatch_count,
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
    print(f"Ignored known pbpstats terminal-row mismatches: {summary['ignored_known_bug_count']}")

    print("\nPer-game results:")
    for game in summary["game_results"]:
        print(
            "  "
            f"{game['game_id']} "
            f"{game['season_year']} {game['season_type']} "
            f"{game['away_team_abbreviation']}@{game['home_team_abbreviation']} "
            f"rows={game['row_count']} mismatches={game['mismatch_count']} ignored={game['ignored_known_bug_count']}"
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
                f"actionType={example['actionType']} subType={example['subType']}"
            )
    else:
        print("  none")


def main() -> int:
    args = parse_args()
    fields = selected_fields(args.phase)
    games = load_validation_games(args.game_set_csv, args.game_ids, args.limit)
    summary = compare_games(games, fields, args.max_examples)

    print_summary(summary)

    if args.json_output is not None:
        args.json_output.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        print(f"\nJSON summary written to {args.json_output}")

    return 1 if summary["mismatch_count"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
