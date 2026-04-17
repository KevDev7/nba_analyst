"""
Build gold agg_team_season from core gold facts, dimensions, and team possession context.

Reads:
  s3://nba-analytics-lakehouse-dev/gold/fct_team_game/fct_team_game.parquet
  s3://nba-analytics-lakehouse-dev/gold/dim_team/dim_team.parquet
  s3://nba-analytics-lakehouse-dev/silver/team_game_possession_context.parquet
  s3://nba-analytics-lakehouse-dev/silver/team_game_defensive_shot_context.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/gold/agg_team_season/agg_team_season.parquet
  s3://nba-analytics-lakehouse-dev/gold/team_season_provenance_sidecar/team_season_provenance_sidecar.parquet
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold.gold_transform_helpers import (
        S3_BUCKET,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        safe_ratio,
        season_type_label_from_code,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        safe_ratio,
        season_type_label_from_code,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )

load_dotenv(override=True)

FACT_SOURCE_KEY = "gold/fct_team_game/fct_team_game.parquet"
DIM_TEAM_SOURCE_KEY = "gold/dim_team/dim_team.parquet"
TEAM_GAME_POSSESSION_CONTEXT_SOURCE_KEY = "silver/team_game_possession_context.parquet"
TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY = "silver/team_game_defensive_shot_context.parquet"
DESTINATION_KEY = "gold/agg_team_season/agg_team_season.parquet"
PROVENANCE_DESTINATION_KEY = (
    "gold/team_season_provenance_sidecar/team_season_provenance_sidecar.parquet"
)

RECORD_SOURCE = (
    "gold.fct_team_game|gold.dim_team|silver.team_game_possession_context|"
    "silver.team_game_defensive_shot_context"
)

FACT_REQUIRED_COLUMNS = [
    "fct_team_game_sk",
    "game_id",
    "team_id",
    "opponent_team_id",
    "score",
    "opponent_score",
    "point_diff",
    "is_home_team",
    "is_in_bonus",
    "timeouts_remaining",
    "seconds_played_total",
    "assists",
    "blocks",
    "blocks_received",
    "field_goals_attempted",
    "field_goals_made",
    "fouls_offensive",
    "fouls_drawn",
    "fouls_personal",
    "fouls_technical",
    "free_throws_attempted",
    "free_throws_made",
    "rebounds_defensive",
    "rebounds_offensive",
    "rebounds_total",
    "steals",
    "turnovers",
    "three_pointers_attempted",
    "three_pointers_made",
    "two_pointers_attempted",
    "two_pointers_made",
    "points_fast_break",
    "points_in_the_paint",
    "points_second_chance",
    "is_win",
    "is_loss",
    "is_tie",
    "season_year",
    "season_start_year",
    "raw_season_type_code",
    "season_type",
    "updated_at_utc",
]

DIM_TEAM_REQUIRED_COLUMNS = [
    "team_id",
    "team_sk",
    "is_current",
    "valid_from_utc",
]

TEAM_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "exact_game_flag",
    "ot_fallback_game_flag",
    "event_estimated_game_flag",
    "boxscore_estimated_game_flag",
    "missing_game_flag",
    "offensive_possessions",
    "defensive_possessions",
]

TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "exact_game_flag",
    "event_estimated_game_flag",
    "boxscore_estimated_game_flag",
    "missing_game_flag",
    "opponent_two_point_attempts",
]

POSSESSION_TOTAL_FIELDS = [
    "offensive_possessions_total",
    "defensive_possessions_total",
]

POSSESSION_COUNTER_FIELDS = [
    "exact_possession_games",
    "ot_fallback_possession_games",
    "event_estimated_possession_games",
    "boxscore_estimated_possession_games",
    "missing_possession_games",
]

SHOT_CONTEXT_TOTAL_FIELDS = [
    "opponent_two_point_attempts_total",
]

SHOT_CONTEXT_COUNTER_FIELDS = [
    "exact_shot_context_games",
    "event_estimated_shot_context_games",
    "boxscore_estimated_shot_context_games",
    "missing_shot_context_games",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("agg_team_season_sk", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("current_team_sk", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("games_played", pa.int64()),
        pa.field("wins", pa.int64()),
        pa.field("losses", pa.int64()),
        pa.field("ties", pa.int64()),
        pa.field("win_percentage", pa.float64()),
        pa.field("points_for_total", pa.int64()),
        pa.field("points_against_total", pa.int64()),
        pa.field("point_diff_total", pa.int64()),
        pa.field("points_for_per_game", pa.float64()),
        pa.field("points_against_per_game", pa.float64()),
        pa.field("point_differential_per_game", pa.float64()),
        pa.field("home_games", pa.int64()),
        pa.field("away_games", pa.int64()),
        pa.field("home_wins", pa.int64()),
        pa.field("away_wins", pa.int64()),
        pa.field("distinct_opponent_count", pa.int64()),
        pa.field("seconds_played_total", pa.float64()),
        pa.field("seconds_played_average", pa.float64()),
        pa.field("assists_total", pa.int64()),
        pa.field("blocks_total", pa.int64()),
        pa.field("blocks_received_total", pa.int64()),
        pa.field("field_goals_attempted_total", pa.int64()),
        pa.field("field_goals_made_total", pa.int64()),
        pa.field("field_goals_percentage", pa.float64()),
        pa.field("fouls_offensive_total", pa.int64()),
        pa.field("fouls_drawn_total", pa.int64()),
        pa.field("fouls_personal_total", pa.int64()),
        pa.field("fouls_technical_total", pa.int64()),
        pa.field("free_throws_attempted_total", pa.int64()),
        pa.field("free_throws_made_total", pa.int64()),
        pa.field("free_throws_percentage", pa.float64()),
        pa.field("rebounds_defensive_total", pa.int64()),
        pa.field("rebounds_offensive_total", pa.int64()),
        pa.field("rebounds_total", pa.int64()),
        pa.field("steals_total", pa.int64()),
        pa.field("turnovers_total", pa.int64()),
        pa.field("three_pointers_attempted_total", pa.int64()),
        pa.field("three_pointers_made_total", pa.int64()),
        pa.field("three_pointers_percentage", pa.float64()),
        pa.field("two_pointers_attempted_total", pa.int64()),
        pa.field("two_pointers_made_total", pa.int64()),
        pa.field("two_pointers_percentage", pa.float64()),
        pa.field("points_fast_break_total", pa.int64()),
        pa.field("points_in_the_paint_total", pa.int64()),
        pa.field("points_second_chance_total", pa.int64()),
        pa.field("in_bonus_count", pa.int64()),
        pa.field("timeouts_remaining_total", pa.int64()),
        pa.field("offensive_possessions_total", pa.float64()),
        pa.field("defensive_possessions_total", pa.float64()),
        pa.field("possessions_total", pa.float64()),
        pa.field("opponent_two_point_attempts_total", pa.float64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)

PROVENANCE_TARGET_SCHEMA = pa.schema(
    [
        pa.field("team_season_provenance_sidecar_sk", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("current_team_sk", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("exact_possession_games", pa.int64()),
        pa.field("ot_fallback_possession_games", pa.int64()),
        pa.field("event_estimated_possession_games", pa.int64()),
        pa.field("boxscore_estimated_possession_games", pa.int64()),
        pa.field("missing_possession_games", pa.int64()),
        pa.field("exact_shot_context_games", pa.int64()),
        pa.field("event_estimated_shot_context_games", pa.int64()),
        pa.field("boxscore_estimated_shot_context_games", pa.int64()),
        pa.field("missing_shot_context_games", pa.int64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)

SUM_FIELDS: list[tuple[str, str]] = [
    ("assists", "assists_total"),
    ("blocks", "blocks_total"),
    ("blocks_received", "blocks_received_total"),
    ("field_goals_attempted", "field_goals_attempted_total"),
    ("field_goals_made", "field_goals_made_total"),
    ("fouls_offensive", "fouls_offensive_total"),
    ("fouls_drawn", "fouls_drawn_total"),
    ("fouls_personal", "fouls_personal_total"),
    ("fouls_technical", "fouls_technical_total"),
    ("free_throws_attempted", "free_throws_attempted_total"),
    ("free_throws_made", "free_throws_made_total"),
    ("rebounds_defensive", "rebounds_defensive_total"),
    ("rebounds_offensive", "rebounds_offensive_total"),
    ("rebounds_total", "rebounds_total"),
    ("steals", "steals_total"),
    ("turnovers", "turnovers_total"),
    ("three_pointers_attempted", "three_pointers_attempted_total"),
    ("three_pointers_made", "three_pointers_made_total"),
    ("two_pointers_attempted", "two_pointers_attempted_total"),
    ("two_pointers_made", "two_pointers_made_total"),
    ("points_fast_break", "points_fast_break_total"),
    ("points_in_the_paint", "points_in_the_paint_total"),
    ("points_second_chance", "points_second_chance_total"),
]


def build_current_team_sk_map(dim_team_table: pa.Table) -> dict[int, int]:
    latest_rows: dict[int, tuple[int, datetime | None]] = {}

    for row in dim_team_table.to_pylist():
        team_id = to_int_or_none(row.get("team_id"))
        team_sk = to_int_or_none(row.get("team_sk"))
        if team_id is None or team_sk is None or to_int_or_none(row.get("is_current")) != 1:
            continue

        valid_from = parse_timestamp_utc(row.get("valid_from_utc"))
        current = latest_rows.get(team_id)
        if current is None or (current[1] or datetime.min.replace(tzinfo=timezone.utc)) < (
            valid_from or datetime.min.replace(tzinfo=timezone.utc)
        ):
            latest_rows[team_id] = (team_sk, valid_from)

    return {team_id: team_sk for team_id, (team_sk, _) in latest_rows.items()}


def _dedupe_fact_rows(fact_table: pa.Table) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, int], dict[str, Any]] = {}

    for row in fact_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue

        key = (game_id, team_id)
        candidate = dict(row)
        current = deduped.get(key)
        if current is None:
            deduped[key] = candidate
            continue

        current_ts = parse_timestamp_utc(current.get("updated_at_utc"))
        candidate_ts = parse_timestamp_utc(candidate.get("updated_at_utc"))
        current_rank = (
            current_ts or datetime.min.replace(tzinfo=timezone.utc),
            to_int_or_none(current.get("fct_team_game_sk")) or 0,
        )
        candidate_rank = (
            candidate_ts or datetime.min.replace(tzinfo=timezone.utc),
            to_int_or_none(candidate.get("fct_team_game_sk")) or 0,
        )
        if candidate_rank > current_rank:
            deduped[key] = candidate

    return list(deduped.values())


def _init_agg(
    *,
    team_id: int,
    season_year: str,
    season_start_year: int,
    raw_season_type_code: str,
    season_type: str,
) -> dict[str, Any]:
    agg = {
        "team_id": team_id,
        "season_year": season_year,
        "season_start_year": season_start_year,
        "raw_season_type_code": raw_season_type_code,
        "season_type": season_type,
        "games_played": 0,
        "wins": 0,
        "losses": 0,
        "ties": 0,
        "home_games": 0,
        "away_games": 0,
        "home_wins": 0,
        "away_wins": 0,
        "points_for_total": 0,
        "points_against_total": 0,
        "point_diff_total": 0,
        "seconds_played_total": 0.0,
        "in_bonus_count": 0,
        "timeouts_remaining_total": 0,
        "_opponents": set(),
    }
    for _, agg_field in SUM_FIELDS:
        agg[agg_field] = 0
    for agg_field in POSSESSION_COUNTER_FIELDS:
        agg[agg_field] = 0
    for agg_field in POSSESSION_TOTAL_FIELDS:
        agg[agg_field] = 0.0
    for agg_field in SHOT_CONTEXT_COUNTER_FIELDS:
        agg[agg_field] = 0
    for agg_field in SHOT_CONTEXT_TOTAL_FIELDS:
        agg[agg_field] = 0.0
    return agg


def build_team_game_possession_map_from_table(
    team_game_possession_context_table: pa.Table,
) -> dict[tuple[str, int], dict[str, float | int]]:
    team_game_possession_map: dict[tuple[str, int], dict[str, float | int]] = {}
    for row in team_game_possession_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        team_game_possession_map[(game_id, team_id)] = {
            "exact_possession_games": to_int_or_none(row.get("exact_game_flag")) or 0,
            "ot_fallback_possession_games": to_int_or_none(row.get("ot_fallback_game_flag")) or 0,
            "event_estimated_possession_games": to_int_or_none(row.get("event_estimated_game_flag")) or 0,
            "boxscore_estimated_possession_games": to_int_or_none(row.get("boxscore_estimated_game_flag")) or 0,
            "missing_possession_games": to_int_or_none(row.get("missing_game_flag")) or 0,
            "offensive_possessions_total": to_float_or_none(row.get("offensive_possessions")) or 0.0,
            "defensive_possessions_total": to_float_or_none(row.get("defensive_possessions")) or 0.0,
        }
    return team_game_possession_map


def build_team_game_defensive_shot_context_map_from_table(
    team_game_defensive_shot_context_table: pa.Table,
) -> dict[tuple[str, int], dict[str, float | int]]:
    shot_context_map: dict[tuple[str, int], dict[str, float | int]] = {}
    for row in team_game_defensive_shot_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        shot_context_map[(game_id, team_id)] = {
            "exact_shot_context_games": to_int_or_none(row.get("exact_game_flag")) or 0,
            "event_estimated_shot_context_games": to_int_or_none(row.get("event_estimated_game_flag")) or 0,
            "boxscore_estimated_shot_context_games": to_int_or_none(row.get("boxscore_estimated_game_flag")) or 0,
            "missing_shot_context_games": to_int_or_none(row.get("missing_game_flag")) or 0,
            "opponent_two_point_attempts_total": to_float_or_none(row.get("opponent_two_point_attempts")) or 0.0,
        }
    return shot_context_map


def build_agg_rows(
    fact_table: pa.Table,
    current_team_sk_map: dict[int, int],
    team_game_possession_map: dict[tuple[str, int], dict[str, float | int]] | None = None,
    team_game_shot_context_map: dict[tuple[str, int], dict[str, float | int]] | None = None,
) -> list[dict[str, Any]]:
    deduped_rows = _dedupe_fact_rows(fact_table)
    aggregations: dict[tuple[int, str, int, str], dict[str, Any]] = {}

    for row in deduped_rows:
        team_id = to_int_or_none(row.get("team_id"))
        season_year = to_str_or_none(row.get("season_year"))
        season_start_year = to_int_or_none(row.get("season_start_year"))
        raw_season_type_code = to_str_or_none(row.get("raw_season_type_code"))
        if team_id is None or season_year is None or season_start_year is None or raw_season_type_code is None:
            continue

        season_type = to_str_or_none(row.get("season_type")) or season_type_label_from_code(raw_season_type_code) or "unknown"
        key = (team_id, season_year, season_start_year, raw_season_type_code)
        agg = aggregations.get(key)
        if agg is None:
            agg = _init_agg(
                team_id=team_id,
                season_year=season_year,
                season_start_year=season_start_year,
                raw_season_type_code=raw_season_type_code,
                season_type=season_type,
            )
            aggregations[key] = agg

        agg["games_played"] += 1
        agg["wins"] += 1 if to_int_or_none(row.get("is_win")) == 1 else 0
        agg["losses"] += 1 if to_int_or_none(row.get("is_loss")) == 1 else 0
        agg["ties"] += 1 if to_int_or_none(row.get("is_tie")) == 1 else 0

        is_home_team = to_int_or_none(row.get("is_home_team"))
        if is_home_team == 1:
            agg["home_games"] += 1
            agg["home_wins"] += 1 if to_int_or_none(row.get("is_win")) == 1 else 0
        elif is_home_team == 0:
            agg["away_games"] += 1
            agg["away_wins"] += 1 if to_int_or_none(row.get("is_win")) == 1 else 0

        opponent_team_id = to_int_or_none(row.get("opponent_team_id"))
        if opponent_team_id is not None:
            agg["_opponents"].add(opponent_team_id)

        agg["points_for_total"] += to_int_or_none(row.get("score")) or 0
        agg["points_against_total"] += to_int_or_none(row.get("opponent_score")) or 0
        agg["point_diff_total"] += to_int_or_none(row.get("point_diff")) or 0
        agg["seconds_played_total"] += to_float_or_none(row.get("seconds_played_total")) or 0.0
        agg["in_bonus_count"] += to_int_or_none(row.get("is_in_bonus")) or 0
        agg["timeouts_remaining_total"] += to_int_or_none(row.get("timeouts_remaining")) or 0

        for source_field, agg_field in SUM_FIELDS:
            agg[agg_field] += to_int_or_none(row.get(source_field)) or 0

        game_id = to_str_or_none(row.get("game_id"))
        if game_id is not None:
            possession_stats = (team_game_possession_map or {}).get((game_id, team_id))
            if possession_stats is not None:
                for agg_field in POSSESSION_COUNTER_FIELDS:
                    agg[agg_field] += to_int_or_none(possession_stats.get(agg_field)) or 0
                for agg_field in POSSESSION_TOTAL_FIELDS:
                    agg[agg_field] += to_float_or_none(possession_stats.get(agg_field)) or 0.0

            shot_context_stats = (team_game_shot_context_map or {}).get((game_id, team_id))
            if shot_context_stats is not None:
                for agg_field in SHOT_CONTEXT_COUNTER_FIELDS:
                    agg[agg_field] += to_int_or_none(shot_context_stats.get(agg_field)) or 0
                for agg_field in SHOT_CONTEXT_TOTAL_FIELDS:
                    agg[agg_field] += to_float_or_none(shot_context_stats.get(agg_field)) or 0.0

    rows: list[dict[str, Any]] = []
    for agg in aggregations.values():
        row = {
            "team_id": agg["team_id"],
            "current_team_sk": current_team_sk_map.get(agg["team_id"]),
            "season_year": agg["season_year"],
            "season_start_year": agg["season_start_year"],
            "raw_season_type_code": agg["raw_season_type_code"],
            "season_type": agg["season_type"],
            "games_played": agg["games_played"],
            "wins": agg["wins"],
            "losses": agg["losses"],
            "ties": agg["ties"],
            "win_percentage": safe_ratio(agg["wins"], agg["games_played"]),
            "points_for_total": agg["points_for_total"],
            "points_against_total": agg["points_against_total"],
            "point_diff_total": agg["point_diff_total"],
            "points_for_per_game": safe_ratio(agg["points_for_total"], agg["games_played"]),
            "points_against_per_game": safe_ratio(agg["points_against_total"], agg["games_played"]),
            "point_differential_per_game": safe_ratio(agg["point_diff_total"], agg["games_played"]),
            "home_games": agg["home_games"],
            "away_games": agg["away_games"],
            "home_wins": agg["home_wins"],
            "away_wins": agg["away_wins"],
            "distinct_opponent_count": len(agg["_opponents"]),
            "seconds_played_total": agg["seconds_played_total"],
            "seconds_played_average": safe_ratio(agg["seconds_played_total"], agg["games_played"]),
            "assists_total": agg["assists_total"],
            "blocks_total": agg["blocks_total"],
            "blocks_received_total": agg["blocks_received_total"],
            "field_goals_attempted_total": agg["field_goals_attempted_total"],
            "field_goals_made_total": agg["field_goals_made_total"],
            "field_goals_percentage": safe_ratio(agg["field_goals_made_total"], agg["field_goals_attempted_total"]),
            "fouls_offensive_total": agg["fouls_offensive_total"],
            "fouls_drawn_total": agg["fouls_drawn_total"],
            "fouls_personal_total": agg["fouls_personal_total"],
            "fouls_technical_total": agg["fouls_technical_total"],
            "free_throws_attempted_total": agg["free_throws_attempted_total"],
            "free_throws_made_total": agg["free_throws_made_total"],
            "free_throws_percentage": safe_ratio(agg["free_throws_made_total"], agg["free_throws_attempted_total"]),
            "rebounds_defensive_total": agg["rebounds_defensive_total"],
            "rebounds_offensive_total": agg["rebounds_offensive_total"],
            "rebounds_total": agg["rebounds_total"],
            "steals_total": agg["steals_total"],
            "turnovers_total": agg["turnovers_total"],
            "three_pointers_attempted_total": agg["three_pointers_attempted_total"],
            "three_pointers_made_total": agg["three_pointers_made_total"],
            "three_pointers_percentage": safe_ratio(
                agg["three_pointers_made_total"], agg["three_pointers_attempted_total"]
            ),
            "two_pointers_attempted_total": agg["two_pointers_attempted_total"],
            "two_pointers_made_total": agg["two_pointers_made_total"],
            "two_pointers_percentage": safe_ratio(
                agg["two_pointers_made_total"], agg["two_pointers_attempted_total"]
            ),
            "points_fast_break_total": agg["points_fast_break_total"],
            "points_in_the_paint_total": agg["points_in_the_paint_total"],
            "points_second_chance_total": agg["points_second_chance_total"],
            "in_bonus_count": agg["in_bonus_count"],
            "timeouts_remaining_total": agg["timeouts_remaining_total"],
            "exact_possession_games": agg["exact_possession_games"],
            "ot_fallback_possession_games": agg["ot_fallback_possession_games"],
            "event_estimated_possession_games": agg["event_estimated_possession_games"],
            "boxscore_estimated_possession_games": agg["boxscore_estimated_possession_games"],
            "missing_possession_games": agg["missing_possession_games"],
            "offensive_possessions_total": agg["offensive_possessions_total"],
            "defensive_possessions_total": agg["defensive_possessions_total"],
            "possessions_total": agg["offensive_possessions_total"] + agg["defensive_possessions_total"],
            "exact_shot_context_games": agg["exact_shot_context_games"],
            "event_estimated_shot_context_games": agg["event_estimated_shot_context_games"],
            "boxscore_estimated_shot_context_games": agg["boxscore_estimated_shot_context_games"],
            "missing_shot_context_games": agg["missing_shot_context_games"],
            "opponent_two_point_attempts_total": agg["opponent_two_point_attempts_total"],
        }
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row.get("team_id") if row.get("team_id") is not None else -1,
            row.get("season_start_year") if row.get("season_start_year") is not None else -1,
            row.get("raw_season_type_code") or "",
        )
    )
    return rows


def _rows_for_schema(rows: list[dict[str, Any]], schema: pa.Schema) -> list[dict[str, Any]]:
    schema_fields = schema.names
    return [{field: row.get(field) for field in schema_fields} for row in rows]


def build_public_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _rows_for_schema(rows, TARGET_SCHEMA)


def build_provenance_sidecar_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _rows_for_schema(rows, PROVENANCE_TARGET_SCHEMA)


def finalize_rows(
    rows: list[dict[str, Any]],
    *,
    surrogate_key_field: str,
    run_ts: datetime | None = None,
) -> list[dict[str, Any]]:
    run_ts = run_ts or datetime.now(timezone.utc)
    for index, row in enumerate(rows, start=1):
        row[surrogate_key_field] = index
        row["record_source"] = RECORD_SOURCE
        row["created_at_utc"] = run_ts
        row["updated_at_utc"] = run_ts
    return rows


def main() -> None:
    s3_client = boto3.client("s3")

    fact_table = read_parquet_table_from_s3(s3_client, FACT_SOURCE_KEY, FACT_REQUIRED_COLUMNS)
    dim_team_table = read_parquet_table_from_s3(s3_client, DIM_TEAM_SOURCE_KEY, DIM_TEAM_REQUIRED_COLUMNS)
    team_game_possession_context_table = read_parquet_table_from_s3(
        s3_client,
        TEAM_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        TEAM_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS,
    )
    team_game_defensive_shot_context_table = read_parquet_table_from_s3(
        s3_client,
        TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS,
    )

    rows = build_agg_rows(
        fact_table,
        build_current_team_sk_map(dim_team_table),
        build_team_game_possession_map_from_table(team_game_possession_context_table),
        build_team_game_defensive_shot_context_map_from_table(team_game_defensive_shot_context_table),
    )
    run_ts = datetime.now(timezone.utc)
    public_rows = finalize_rows(
        build_public_rows(rows),
        surrogate_key_field="agg_team_season_sk",
        run_ts=run_ts,
    )
    provenance_rows = finalize_rows(
        build_provenance_sidecar_rows(rows),
        surrogate_key_field="team_season_provenance_sidecar_sk",
        run_ts=run_ts,
    )
    write_parquet_to_s3(public_rows, TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    write_parquet_to_s3(
        provenance_rows,
        PROVENANCE_TARGET_SCHEMA,
        PROVENANCE_DESTINATION_KEY,
        s3_client,
    )
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")
    print(f"Wrote s3://{S3_BUCKET}/{PROVENANCE_DESTINATION_KEY}")


if __name__ == "__main__":
    main()
