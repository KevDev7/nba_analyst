"""
Build a canonical silver player-game opportunity context table.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet
  s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/on_court_state/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/pbpstats_event_context_v1/game_id=<GAME_ID>.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/silver/player_game_opportunity_context.parquet
"""

from __future__ import annotations

import io
import os
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.silver.silver_pipeline_helpers import write_audit_artifacts
    from pipelines.athena.transform.silver import build_silver_player_game_possession_context as pgpc
except ModuleNotFoundError:
    from silver_pipeline_helpers import write_audit_artifacts  # type: ignore[no-redef]
    import build_silver_player_game_possession_context as pgpc  # type: ignore[no-redef]

load_dotenv(override=True)
if os.getenv("AWS_PROFILE") == "":
    os.environ.pop("AWS_PROFILE", None)
if os.getenv("AWS_DEFAULT_PROFILE") == "":
    os.environ.pop("AWS_DEFAULT_PROFILE", None)

S3_BUCKET = pgpc.S3_BUCKET
PLAYER_SOURCE_KEY = pgpc.PLAYER_SOURCE_KEY
TEAM_SOURCE_KEY = pgpc.TEAM_SOURCE_KEY
SCHEDULE_SOURCE_KEY = pgpc.SCHEDULE_SOURCE_KEY
PLAYBYPLAY_PREFIX = pgpc.PLAYBYPLAY_PREFIX
ON_COURT_PREFIX = pgpc.ON_COURT_PREFIX
EVENT_CONTEXT_PREFIX = "silver/pbpstats_event_context_v1/"
DESTINATION_KEY = "silver/player_game_opportunity_context.parquet"
TABLE_NAME = "player_game_opportunity_context"
META_SOURCE_SYSTEM = (
    "silver_boxscore_player_game|silver_boxscore_team_game|silver_scheduleLeagueV2_1|"
    "silver_playbyplay|silver_on_court_state|silver_pbpstats_event_context_v1"
)
META_SOURCE_KEY = (
    "silver/boxscore_player_game.parquet|silver/boxscore_team_game.parquet|"
    "silver/scheduleLeagueV2_1.parquet|silver/playbyplay/|silver/on_court_state/|"
    "silver/pbpstats_event_context_v1/"
)
META_SCHEMA_VERSION = 1

PLAYER_REQUIRED_COLUMNS = [*pgpc.PLAYER_REQUIRED_COLUMNS, "fieldGoalsMade"]
TEAM_REQUIRED_COLUMNS = [
    "gameId",
    "teamId",
    "minutes",
    "minutesCalculated",
    "fieldGoalsMade",
    "reboundsOffensive",
    "reboundsDefensive",
    "reboundsTotal",
]
SCHEDULE_REQUIRED_COLUMNS = pgpc.SCHEDULE_REQUIRED_COLUMNS
PLAYBYPLAY_REQUIRED_COLUMNS = [
    "gameId",
    "actionNumber",
    "orderNumber",
    "teamId",
    "personId",
    "isFieldGoal",
    "isMadeShot",
    "isRebound",
    "reboundOfMissedShotFlag",
    "isPlaceholderRebound",
    "isOreb",
    "isDreb",
]
ON_COURT_REQUIRED_COLUMNS = pgpc.ON_COURT_REQUIRED_COLUMNS
EVENT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "event_num",
    "home_team_id",
    "away_team_id",
    "home_current_player_ids",
    "away_current_player_ids",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("person_id", pa.int64()),
        pa.field("team_id", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("teammate_field_goals_made_while_on_court", pa.float64()),
        pa.field("offensive_rebound_opportunities_while_on_court", pa.float64()),
        pa.field("defensive_rebound_opportunities_while_on_court", pa.float64()),
        pa.field("rebound_opportunities_while_on_court", pa.float64()),
        pa.field("assist_context_source_method", pa.string()),
        pa.field("assist_exact_count", pa.float64()),
        pa.field("assist_event_estimated_count", pa.float64()),
        pa.field("assist_boxscore_estimated_count", pa.float64()),
        pa.field("assist_missing_count", pa.float64()),
        pa.field("assist_exact_game_flag", pa.int64()),
        pa.field("assist_event_estimated_game_flag", pa.int64()),
        pa.field("assist_boxscore_estimated_game_flag", pa.int64()),
        pa.field("assist_missing_game_flag", pa.int64()),
        pa.field("rebound_context_source_method", pa.string()),
        pa.field("rebound_exact_count", pa.float64()),
        pa.field("rebound_event_estimated_count", pa.float64()),
        pa.field("rebound_boxscore_estimated_count", pa.float64()),
        pa.field("rebound_missing_count", pa.float64()),
        pa.field("rebound_exact_game_flag", pa.int64()),
        pa.field("rebound_event_estimated_game_flag", pa.int64()),
        pa.field("rebound_boxscore_estimated_game_flag", pa.int64()),
        pa.field("rebound_missing_game_flag", pa.int64()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def init_player_stats(person_ids: set[int]) -> dict[int, dict[str, Any]]:
    return {
        person_id: {
            "teammate_field_goals_made_while_on_court": 0.0,
            "offensive_rebound_opportunities_while_on_court": 0.0,
            "defensive_rebound_opportunities_while_on_court": 0.0,
            "rebound_opportunities_while_on_court": 0.0,
            "assist_context_source_method": None,
            "assist_exact_count": 0.0,
            "assist_event_estimated_count": 0.0,
            "assist_boxscore_estimated_count": 0.0,
            "assist_missing_count": 0.0,
            "assist_exact_game_flag": 0,
            "assist_event_estimated_game_flag": 0,
            "assist_boxscore_estimated_game_flag": 0,
            "assist_missing_game_flag": 0,
            "rebound_context_source_method": None,
            "rebound_exact_count": 0.0,
            "rebound_event_estimated_count": 0.0,
            "rebound_boxscore_estimated_count": 0.0,
            "rebound_missing_count": 0.0,
            "rebound_exact_game_flag": 0,
            "rebound_event_estimated_game_flag": 0,
            "rebound_boxscore_estimated_game_flag": 0,
            "rebound_missing_game_flag": 0,
        }
        for person_id in sorted(person_ids)
    }


def build_played_players_by_game(player_table: pa.Table) -> dict[str, dict[int, dict[str, Any]]]:
    rows_by_game: dict[str, dict[int, dict[str, Any]]] = {}
    for row in player_table.to_pylist():
        game_id = pgpc.normalize_game_id(row.get("gameId"))
        person_id = pgpc.to_int_or_none(row.get("personId"))
        team_id = pgpc.to_int_or_none(row.get("teamId"))
        minutes_seconds = pgpc.parse_iso_duration_seconds(row.get("minutesCalculated"))
        if minutes_seconds is None:
            minutes_seconds = pgpc.parse_iso_duration_seconds(row.get("minutes"))
        played_flag = 1 if pgpc.to_int_or_none(row.get("played")) == 1 or (minutes_seconds or 0.0) > 0 else 0
        if game_id is None or person_id is None or team_id is None or played_flag != 1:
            continue
        rows_by_game.setdefault(game_id, {})[person_id] = {
            "person_id": person_id,
            "team_id": team_id,
            "minutes_seconds_total": minutes_seconds or 0.0,
            "field_goals_made": pgpc.to_int_or_none(row.get("fieldGoalsMade")),
        }
    return rows_by_game


def build_team_context_map(team_table: pa.Table) -> dict[tuple[str, int], dict[str, Any]]:
    context: dict[tuple[str, int], dict[str, Any]] = {}
    teams_by_game: dict[str, list[int]] = {}
    for row in team_table.to_pylist():
        game_id = pgpc.normalize_game_id(row.get("gameId"))
        team_id = pgpc.to_int_or_none(row.get("teamId"))
        if game_id is None or team_id is None:
            continue
        teams_by_game.setdefault(game_id, []).append(team_id)
        minutes_seconds = pgpc.parse_iso_duration_seconds(row.get("minutesCalculated"))
        if minutes_seconds is None:
            minutes_seconds = pgpc.parse_iso_duration_seconds(row.get("minutes"))
        rebounds_offensive = pgpc.to_int_or_none(row.get("reboundsOffensive"))
        rebounds_defensive = pgpc.to_int_or_none(row.get("reboundsDefensive"))
        rebounds_total = pgpc.to_int_or_none(row.get("reboundsTotal"))
        if rebounds_total is None:
            rebounds_total = (rebounds_offensive or 0) + (rebounds_defensive or 0)
        context[(game_id, team_id)] = {
            "minutes_seconds_total": minutes_seconds,
            "field_goals_made": pgpc.to_int_or_none(row.get("fieldGoalsMade")),
            "rebounds_offensive": rebounds_offensive,
            "rebounds_defensive": rebounds_defensive,
            "rebounds_total": rebounds_total,
        }

    for game_id, team_ids in teams_by_game.items():
        unique_team_ids = sorted(set(team_ids))
        if len(unique_team_ids) != 2:
            continue
        first_id, second_id = unique_team_ids
        context[(game_id, first_id)]["opponent_team_id"] = second_id
        context[(game_id, second_id)]["opponent_team_id"] = first_id
    return context


def build_event_context_by_event_num(
    event_context_rows: list[dict[str, Any]] | None,
) -> tuple[int | None, int | None, dict[int, tuple[list[int], list[int]]]]:
    home_team_id = None
    away_team_id = None
    context_by_event_num: dict[int, tuple[list[int], list[int]]] = {}
    for row in event_context_rows or []:
        if home_team_id is None:
            home_team_id = pgpc.to_int_or_none(row.get("home_team_id"))
        if away_team_id is None:
            away_team_id = pgpc.to_int_or_none(row.get("away_team_id"))
        event_num = pgpc.to_int_or_none(row.get("event_num"))
        home_players = pgpc.normalize_player_ids(row.get("home_current_player_ids"))
        away_players = pgpc.normalize_player_ids(row.get("away_current_player_ids"))
        if event_num is None or home_players is None or away_players is None:
            continue
        context_by_event_num[event_num] = (home_players, away_players)
    return home_team_id, away_team_id, context_by_event_num


def is_made_field_goal(row: dict[str, Any]) -> bool:
    return (
        pgpc.to_bool_or_none(row.get("isFieldGoal")) is True
        and pgpc.to_bool_or_none(row.get("isMadeShot")) is True
    )


def is_rebound_opportunity(row: dict[str, Any]) -> bool:
    if pgpc.to_bool_or_none(row.get("isRebound")) is not True:
        return False
    if pgpc.to_bool_or_none(row.get("reboundOfMissedShotFlag")) is not True:
        return False
    if pgpc.to_bool_or_none(row.get("isPlaceholderRebound")) is True:
        return False
    return (
        pgpc.to_bool_or_none(row.get("isOreb")) is True
        or pgpc.to_bool_or_none(row.get("isDreb")) is True
    )


def resolve_team_lineups(
    *,
    team_id: int | None,
    home_team_id: int,
    away_team_id: int,
    home_players: list[int],
    away_players: list[int],
) -> list[int] | None:
    if team_id == home_team_id:
        return home_players
    if team_id == away_team_id:
        return away_players
    return None


def resolve_offense_and_defense_players_from_rebound(
    *,
    rebound_team_id: int | None,
    is_oreb: bool,
    is_dreb: bool,
    home_team_id: int,
    away_team_id: int,
    home_players: list[int],
    away_players: list[int],
) -> tuple[list[int], list[int]] | None:
    if rebound_team_id is None:
        return None
    if is_oreb:
        offense_players = resolve_team_lineups(
            team_id=rebound_team_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_players=home_players,
            away_players=away_players,
        )
        if offense_players is None:
            return None
        defense_players = away_players if offense_players == home_players else home_players
        return offense_players, defense_players
    if is_dreb:
        defense_players = resolve_team_lineups(
            team_id=rebound_team_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_players=home_players,
            away_players=away_players,
        )
        if defense_players is None:
            return None
        offense_players = away_players if defense_players == home_players else home_players
        return offense_players, defense_players
    return None


def assign_teammate_field_goal_made(
    stats: dict[int, dict[str, Any]],
    offense_players: list[int],
    *,
    scorer_id: int | None,
    count_field: str,
) -> None:
    for person_id in offense_players:
        if scorer_id is not None and person_id == scorer_id:
            continue
        player_stats = stats.get(person_id)
        if player_stats is None:
            continue
        player_stats["teammate_field_goals_made_while_on_court"] += 1.0
        player_stats[count_field] += 1.0


def assign_rebound_opportunity(
    stats: dict[int, dict[str, Any]],
    offense_players: list[int],
    defense_players: list[int],
    *,
    count_field: str,
) -> None:
    for person_id in offense_players:
        player_stats = stats.get(person_id)
        if player_stats is None:
            continue
        player_stats["offensive_rebound_opportunities_while_on_court"] += 1.0
        player_stats["rebound_opportunities_while_on_court"] += 1.0
        player_stats[count_field] += 1.0
    for person_id in defense_players:
        player_stats = stats.get(person_id)
        if player_stats is None:
            continue
        player_stats["defensive_rebound_opportunities_while_on_court"] += 1.0
        player_stats["rebound_opportunities_while_on_court"] += 1.0
        player_stats[count_field] += 1.0


def build_exact_assist_context_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    on_court_rows: list[dict[str, Any]] | None,
    played_players: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]] | None:
    on_court_lookup = pgpc.build_on_court_lookup(on_court_rows)
    if on_court_lookup is None:
        return None

    stats = init_player_stats(set(played_players))
    home_team_id = on_court_lookup["home_team_id"]
    away_team_id = on_court_lookup["away_team_id"]
    shot_rows = [row for row in playbyplay_rows or [] if is_made_field_goal(row)]

    for row in shot_rows:
        order_number = pgpc.to_int_or_none(row.get("orderNumber"))
        current_lineups = pgpc.resolve_stint_for_range(
            on_court_lookup,
            start_order=order_number,
            end_order=order_number,
            probe_order=order_number,
        )
        if current_lineups is None:
            return None
        home_players, away_players = current_lineups
        offense_players = resolve_team_lineups(
            team_id=pgpc.to_int_or_none(row.get("teamId")),
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_players=home_players,
            away_players=away_players,
        )
        if offense_players is None:
            return None
        assign_teammate_field_goal_made(
            stats,
            offense_players,
            scorer_id=pgpc.to_int_or_none(row.get("personId")),
            count_field="assist_exact_count",
        )

    for player_stats in stats.values():
        player_stats["assist_context_source_method"] = "exact"
        player_stats["assist_exact_game_flag"] = 1
    return stats


def build_event_estimated_assist_context_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
    played_players: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]] | None:
    if not event_context_rows:
        return None
    home_team_id, away_team_id, context_by_event_num = build_event_context_by_event_num(event_context_rows)
    if home_team_id is None or away_team_id is None or not context_by_event_num:
        return None

    stats = init_player_stats(set(played_players))
    shot_rows = [row for row in playbyplay_rows or [] if is_made_field_goal(row)]

    for row in shot_rows:
        action_number = pgpc.to_int_or_none(row.get("actionNumber"))
        context = context_by_event_num.get(action_number or -1)
        if context is None:
            return None
        home_players, away_players = context
        offense_players = resolve_team_lineups(
            team_id=pgpc.to_int_or_none(row.get("teamId")),
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_players=home_players,
            away_players=away_players,
        )
        if offense_players is None:
            return None
        assign_teammate_field_goal_made(
            stats,
            offense_players,
            scorer_id=pgpc.to_int_or_none(row.get("personId")),
            count_field="assist_event_estimated_count",
        )

    for player_stats in stats.values():
        player_stats["assist_context_source_method"] = "event_estimated"
        player_stats["assist_event_estimated_game_flag"] = 1
    return stats


def build_boxscore_estimated_assist_context_stats(
    played_players: dict[int, dict[str, Any]],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    *,
    game_id: str,
) -> dict[int, dict[str, Any]] | None:
    if not played_players:
        return None
    stats = init_player_stats(set(played_players))

    for person_id, player_info in played_players.items():
        team_id = pgpc.to_int_or_none(player_info.get("team_id"))
        if team_id is None:
            return None
        team_row = team_context_map.get((game_id, team_id))
        if team_row is None:
            return None

        team_minutes_seconds_total = pgpc.to_float_or_none(team_row.get("minutes_seconds_total"))
        player_minutes_seconds_total = pgpc.to_float_or_none(player_info.get("minutes_seconds_total")) or 0.0
        if team_minutes_seconds_total is None or team_minutes_seconds_total <= 0:
            return None

        minute_share = player_minutes_seconds_total / (team_minutes_seconds_total / 5.0)
        team_field_goals_made = float(pgpc.to_int_or_none(team_row.get("field_goals_made")) or 0)
        player_field_goals_made = float(
            pgpc.to_int_or_none(player_info.get("field_goals_made"))
            or pgpc.to_int_or_none(player_info.get("fieldGoalsMade"))
            or 0
        )
        estimated_teammate_fgm = max((minute_share * team_field_goals_made) - player_field_goals_made, 0.0)

        player_stats = stats[person_id]
        player_stats["teammate_field_goals_made_while_on_court"] = estimated_teammate_fgm
        player_stats["assist_boxscore_estimated_count"] = estimated_teammate_fgm
        player_stats["assist_context_source_method"] = "boxscore_estimated"
        player_stats["assist_boxscore_estimated_game_flag"] = 1
    return stats


def build_missing_assist_context_stats(played_players: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    stats = init_player_stats(set(played_players))
    for player_stats in stats.values():
        player_stats["assist_context_source_method"] = "missing"
        player_stats["assist_missing_game_flag"] = 1
    return stats


def choose_assist_context_stats(
    *,
    game_id: str,
    played_players: dict[int, dict[str, Any]],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    playbyplay_rows: list[dict[str, Any]] | None,
    on_court_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    exact_stats = build_exact_assist_context_stats(playbyplay_rows, on_court_rows, played_players)
    if exact_stats is not None:
        return exact_stats

    event_stats = build_event_estimated_assist_context_stats(
        playbyplay_rows,
        event_context_rows,
        played_players,
    )
    if event_stats is not None:
        return event_stats

    boxscore_stats = build_boxscore_estimated_assist_context_stats(
        played_players,
        team_context_map,
        game_id=game_id,
    )
    if boxscore_stats is not None:
        return boxscore_stats

    return build_missing_assist_context_stats(played_players)


def build_exact_rebound_context_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    on_court_rows: list[dict[str, Any]] | None,
    played_players: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]] | None:
    on_court_lookup = pgpc.build_on_court_lookup(on_court_rows)
    if on_court_lookup is None:
        return None

    stats = init_player_stats(set(played_players))
    home_team_id = on_court_lookup["home_team_id"]
    away_team_id = on_court_lookup["away_team_id"]
    rebound_rows = [row for row in playbyplay_rows or [] if is_rebound_opportunity(row)]

    for row in rebound_rows:
        order_number = pgpc.to_int_or_none(row.get("orderNumber"))
        current_lineups = pgpc.resolve_stint_for_range(
            on_court_lookup,
            start_order=order_number,
            end_order=order_number,
            probe_order=order_number,
        )
        if current_lineups is None:
            return None
        home_players, away_players = current_lineups
        resolved_players = resolve_offense_and_defense_players_from_rebound(
            rebound_team_id=pgpc.to_int_or_none(row.get("teamId")),
            is_oreb=pgpc.to_bool_or_none(row.get("isOreb")) is True,
            is_dreb=pgpc.to_bool_or_none(row.get("isDreb")) is True,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_players=home_players,
            away_players=away_players,
        )
        if resolved_players is None:
            return None
        offense_players, defense_players = resolved_players
        assign_rebound_opportunity(
            stats,
            offense_players,
            defense_players,
            count_field="rebound_exact_count",
        )

    for player_stats in stats.values():
        player_stats["rebound_context_source_method"] = "exact"
        player_stats["rebound_exact_game_flag"] = 1
    return stats


def build_event_estimated_rebound_context_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
    played_players: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]] | None:
    if not event_context_rows:
        return None
    home_team_id, away_team_id, context_by_event_num = build_event_context_by_event_num(event_context_rows)
    if home_team_id is None or away_team_id is None or not context_by_event_num:
        return None

    stats = init_player_stats(set(played_players))
    rebound_rows = [row for row in playbyplay_rows or [] if is_rebound_opportunity(row)]

    for row in rebound_rows:
        action_number = pgpc.to_int_or_none(row.get("actionNumber"))
        context = context_by_event_num.get(action_number or -1)
        if context is None:
            return None
        home_players, away_players = context
        resolved_players = resolve_offense_and_defense_players_from_rebound(
            rebound_team_id=pgpc.to_int_or_none(row.get("teamId")),
            is_oreb=pgpc.to_bool_or_none(row.get("isOreb")) is True,
            is_dreb=pgpc.to_bool_or_none(row.get("isDreb")) is True,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_players=home_players,
            away_players=away_players,
        )
        if resolved_players is None:
            return None
        offense_players, defense_players = resolved_players
        assign_rebound_opportunity(
            stats,
            offense_players,
            defense_players,
            count_field="rebound_event_estimated_count",
        )

    for player_stats in stats.values():
        player_stats["rebound_context_source_method"] = "event_estimated"
        player_stats["rebound_event_estimated_game_flag"] = 1
    return stats


def build_boxscore_estimated_rebound_context_stats(
    played_players: dict[int, dict[str, Any]],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    *,
    game_id: str,
) -> dict[int, dict[str, Any]] | None:
    if not played_players:
        return None
    stats = init_player_stats(set(played_players))

    for person_id, player_info in played_players.items():
        team_id = pgpc.to_int_or_none(player_info.get("team_id"))
        if team_id is None:
            return None
        team_row = team_context_map.get((game_id, team_id))
        if team_row is None:
            return None
        opponent_team_id = pgpc.to_int_or_none(team_row.get("opponent_team_id"))
        if opponent_team_id is None:
            return None
        opponent_row = team_context_map.get((game_id, opponent_team_id))
        if opponent_row is None:
            return None

        team_minutes_seconds_total = pgpc.to_float_or_none(team_row.get("minutes_seconds_total"))
        player_minutes_seconds_total = pgpc.to_float_or_none(player_info.get("minutes_seconds_total")) or 0.0
        if team_minutes_seconds_total is None or team_minutes_seconds_total <= 0:
            return None

        minute_share = player_minutes_seconds_total / (team_minutes_seconds_total / 5.0)
        team_oreb = float(pgpc.to_int_or_none(team_row.get("rebounds_offensive")) or 0)
        team_dreb = float(pgpc.to_int_or_none(team_row.get("rebounds_defensive")) or 0)
        team_reb = float(pgpc.to_int_or_none(team_row.get("rebounds_total")) or 0)
        opponent_oreb = float(pgpc.to_int_or_none(opponent_row.get("rebounds_offensive")) or 0)
        opponent_dreb = float(pgpc.to_int_or_none(opponent_row.get("rebounds_defensive")) or 0)
        opponent_reb = float(pgpc.to_int_or_none(opponent_row.get("rebounds_total")) or 0)

        estimated_oreb_opportunities = minute_share * (team_oreb + opponent_dreb)
        estimated_dreb_opportunities = minute_share * (team_dreb + opponent_oreb)
        estimated_rebound_opportunities = minute_share * (team_reb + opponent_reb)

        player_stats = stats[person_id]
        player_stats["offensive_rebound_opportunities_while_on_court"] = estimated_oreb_opportunities
        player_stats["defensive_rebound_opportunities_while_on_court"] = estimated_dreb_opportunities
        player_stats["rebound_opportunities_while_on_court"] = estimated_rebound_opportunities
        player_stats["rebound_boxscore_estimated_count"] = estimated_rebound_opportunities
        player_stats["rebound_context_source_method"] = "boxscore_estimated"
        player_stats["rebound_boxscore_estimated_game_flag"] = 1
    return stats


def build_missing_rebound_context_stats(played_players: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    stats = init_player_stats(set(played_players))
    for player_stats in stats.values():
        player_stats["rebound_context_source_method"] = "missing"
        player_stats["rebound_missing_game_flag"] = 1
    return stats


def choose_rebound_context_stats(
    *,
    game_id: str,
    played_players: dict[int, dict[str, Any]],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    playbyplay_rows: list[dict[str, Any]] | None,
    on_court_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    exact_stats = build_exact_rebound_context_stats(playbyplay_rows, on_court_rows, played_players)
    if exact_stats is not None:
        return exact_stats

    event_stats = build_event_estimated_rebound_context_stats(
        playbyplay_rows,
        event_context_rows,
        played_players,
    )
    if event_stats is not None:
        return event_stats

    boxscore_stats = build_boxscore_estimated_rebound_context_stats(
        played_players,
        team_context_map,
        game_id=game_id,
    )
    if boxscore_stats is not None:
        return boxscore_stats

    return build_missing_rebound_context_stats(played_players)


def choose_game_stats(
    *,
    game_id: str,
    played_players: dict[int, dict[str, Any]],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    playbyplay_rows: list[dict[str, Any]] | None,
    on_court_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    assist_stats = choose_assist_context_stats(
        game_id=game_id,
        played_players=played_players,
        team_context_map=team_context_map,
        playbyplay_rows=playbyplay_rows,
        on_court_rows=on_court_rows,
        event_context_rows=event_context_rows,
    )
    rebound_stats = choose_rebound_context_stats(
        game_id=game_id,
        played_players=played_players,
        team_context_map=team_context_map,
        playbyplay_rows=playbyplay_rows,
        on_court_rows=on_court_rows,
        event_context_rows=event_context_rows,
    )

    merged_stats = init_player_stats(set(played_players))
    for person_id in sorted(played_players):
        merged_player_stats = merged_stats[person_id]
        assist_player_stats = assist_stats[person_id]
        rebound_player_stats = rebound_stats[person_id]
        for field_name in (
            "teammate_field_goals_made_while_on_court",
            "assist_context_source_method",
            "assist_exact_count",
            "assist_event_estimated_count",
            "assist_boxscore_estimated_count",
            "assist_missing_count",
            "assist_exact_game_flag",
            "assist_event_estimated_game_flag",
            "assist_boxscore_estimated_game_flag",
            "assist_missing_game_flag",
        ):
            merged_player_stats[field_name] = assist_player_stats[field_name]
        for field_name in (
            "offensive_rebound_opportunities_while_on_court",
            "defensive_rebound_opportunities_while_on_court",
            "rebound_opportunities_while_on_court",
            "rebound_context_source_method",
            "rebound_exact_count",
            "rebound_event_estimated_count",
            "rebound_boxscore_estimated_count",
            "rebound_missing_count",
            "rebound_exact_game_flag",
            "rebound_event_estimated_game_flag",
            "rebound_boxscore_estimated_game_flag",
            "rebound_missing_game_flag",
        ):
            merged_player_stats[field_name] = rebound_player_stats[field_name]
    return merged_stats


def finalize_player_game_row(
    *,
    game_id: str,
    person_id: int,
    team_id: int | None,
    stats: dict[str, Any],
    schedule_info: dict[str, Any] | None,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
) -> dict[str, Any]:
    season_year = pgpc.to_str_or_none((schedule_info or {}).get("season_year"))
    season_start_year = pgpc.to_int_or_none((schedule_info or {}).get("season_start_year"))
    season_type_code = pgpc.to_str_or_none((schedule_info or {}).get("season_type_code")) or pgpc.season_type_code_from_game_id(game_id)
    season_type = pgpc.to_str_or_none((schedule_info or {}).get("season_type")) or pgpc.season_type_label_from_code(season_type_code)
    if season_start_year is None:
        season_start_year = pgpc.season_start_year_from_label(season_year) or pgpc.season_start_year_from_game_id(game_id)
    if season_year is None and season_start_year is not None:
        season_year = f"{season_start_year}-{(season_start_year + 1) % 100:02d}"

    return {
        "game_id": game_id,
        "person_id": person_id,
        "team_id": team_id,
        "season_year": season_year,
        "season_start_year": season_start_year,
        "season_type_code": season_type_code,
        "season_type": season_type,
        "teammate_field_goals_made_while_on_court": pgpc.to_float_or_none(
            stats.get("teammate_field_goals_made_while_on_court")
        )
        or 0.0,
        "offensive_rebound_opportunities_while_on_court": pgpc.to_float_or_none(
            stats.get("offensive_rebound_opportunities_while_on_court")
        )
        or 0.0,
        "defensive_rebound_opportunities_while_on_court": pgpc.to_float_or_none(
            stats.get("defensive_rebound_opportunities_while_on_court")
        )
        or 0.0,
        "rebound_opportunities_while_on_court": pgpc.to_float_or_none(
            stats.get("rebound_opportunities_while_on_court")
        )
        or 0.0,
        "assist_context_source_method": pgpc.to_str_or_none(stats.get("assist_context_source_method")),
        "assist_exact_count": pgpc.to_float_or_none(stats.get("assist_exact_count")) or 0.0,
        "assist_event_estimated_count": pgpc.to_float_or_none(stats.get("assist_event_estimated_count")) or 0.0,
        "assist_boxscore_estimated_count": pgpc.to_float_or_none(stats.get("assist_boxscore_estimated_count"))
        or 0.0,
        "assist_missing_count": pgpc.to_float_or_none(stats.get("assist_missing_count")) or 0.0,
        "assist_exact_game_flag": pgpc.to_int_or_none(stats.get("assist_exact_game_flag")) or 0,
        "assist_event_estimated_game_flag": pgpc.to_int_or_none(stats.get("assist_event_estimated_game_flag")) or 0,
        "assist_boxscore_estimated_game_flag": pgpc.to_int_or_none(stats.get("assist_boxscore_estimated_game_flag"))
        or 0,
        "assist_missing_game_flag": pgpc.to_int_or_none(stats.get("assist_missing_game_flag")) or 0,
        "rebound_context_source_method": pgpc.to_str_or_none(stats.get("rebound_context_source_method")),
        "rebound_exact_count": pgpc.to_float_or_none(stats.get("rebound_exact_count")) or 0.0,
        "rebound_event_estimated_count": pgpc.to_float_or_none(stats.get("rebound_event_estimated_count"))
        or 0.0,
        "rebound_boxscore_estimated_count": pgpc.to_float_or_none(stats.get("rebound_boxscore_estimated_count"))
        or 0.0,
        "rebound_missing_count": pgpc.to_float_or_none(stats.get("rebound_missing_count")) or 0.0,
        "rebound_exact_game_flag": pgpc.to_int_or_none(stats.get("rebound_exact_game_flag")) or 0,
        "rebound_event_estimated_game_flag": pgpc.to_int_or_none(stats.get("rebound_event_estimated_game_flag"))
        or 0,
        "rebound_boxscore_estimated_game_flag": pgpc.to_int_or_none(stats.get("rebound_boxscore_estimated_game_flag"))
        or 0,
        "rebound_missing_game_flag": pgpc.to_int_or_none(stats.get("rebound_missing_game_flag")) or 0,
        "_meta_pipeline_run_id": pipeline_run_id,
        "_meta_ingested_at_utc": ingested_at_utc,
        "_meta_source_system": META_SOURCE_SYSTEM,
        "_meta_source_key": META_SOURCE_KEY,
        "_meta_schema_version": META_SCHEMA_VERSION,
    }


def build_rows(
    *,
    s3_client,
    player_table: pa.Table,
    team_table: pa.Table,
    schedule_table: pa.Table,
) -> list[dict[str, Any]]:
    played_players_by_game = build_played_players_by_game(player_table)
    team_context_map = build_team_context_map(team_table)
    schedule_map = pgpc.build_schedule_map(schedule_table)

    playbyplay_game_ids = pgpc.list_partition_game_ids(s3_client, PLAYBYPLAY_PREFIX)
    on_court_game_ids = pgpc.list_partition_game_ids(s3_client, ON_COURT_PREFIX)
    event_context_game_ids = pgpc.list_partition_game_ids(s3_client, EVENT_CONTEXT_PREFIX)

    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = (
        f"player_game_opportunity_context_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )

    def _build_game_rows(game_id: str, played_players: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        playbyplay_rows = pgpc.read_partition_rows(
            s3_client,
            prefix=PLAYBYPLAY_PREFIX,
            game_id=game_id,
            columns=PLAYBYPLAY_REQUIRED_COLUMNS,
            available_ids=playbyplay_game_ids,
        )
        on_court_rows = pgpc.read_partition_rows(
            s3_client,
            prefix=ON_COURT_PREFIX,
            game_id=game_id,
            columns=ON_COURT_REQUIRED_COLUMNS,
            available_ids=on_court_game_ids,
        )
        event_context_rows = pgpc.read_partition_rows(
            s3_client,
            prefix=EVENT_CONTEXT_PREFIX,
            game_id=game_id,
            columns=EVENT_CONTEXT_REQUIRED_COLUMNS,
            available_ids=event_context_game_ids,
        )
        game_stats = choose_game_stats(
            game_id=game_id,
            played_players=played_players,
            team_context_map=team_context_map,
            playbyplay_rows=playbyplay_rows,
            on_court_rows=on_court_rows,
            event_context_rows=event_context_rows,
        )
        schedule_info = schedule_map.get(game_id)
        rows: list[dict[str, Any]] = []
        for person_id, player_info in sorted(played_players.items()):
            rows.append(
                finalize_player_game_row(
                    game_id=game_id,
                    person_id=person_id,
                    team_id=pgpc.to_int_or_none(player_info.get("team_id")),
                    stats=game_stats[person_id],
                    schedule_info=schedule_info,
                    pipeline_run_id=pipeline_run_id,
                    ingested_at_utc=ingested_at_utc,
                )
            )
        return rows

    all_rows: list[dict[str, Any]] = []
    max_workers = min(16, max(1, len(played_players_by_game)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_build_game_rows, game_id, played_players): game_id
            for game_id, played_players in sorted(played_players_by_game.items())
        }
        for future in as_completed(future_map):
            all_rows.extend(future.result())

    all_rows.sort(
        key=lambda row: (
            row.get("game_id") or "",
            row.get("person_id") or -1,
        )
    )
    return all_rows


def write_rows(rows: list[dict[str, Any]], s3_client) -> None:
    table = pa.Table.from_pylist(rows, schema=TARGET_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=DESTINATION_KEY,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def main() -> None:
    s3_client = boto3.client("s3")
    player_table = pgpc.read_root_parquet_table(s3_client, PLAYER_SOURCE_KEY, PLAYER_REQUIRED_COLUMNS)
    team_table = pgpc.read_root_parquet_table(s3_client, TEAM_SOURCE_KEY, TEAM_REQUIRED_COLUMNS)
    schedule_table = pgpc.read_root_parquet_table(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    rows = build_rows(
        s3_client=s3_client,
        player_table=player_table,
        team_table=team_table,
        schedule_table=schedule_table,
    )
    write_rows(rows, s3_client)

    ingested_at_utc = datetime.now(timezone.utc)
    assist_method_counts = Counter(row.get("assist_context_source_method") or "unknown" for row in rows)
    rebound_method_counts = Counter(row.get("rebound_context_source_method") or "unknown" for row in rows)
    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": rows[0]["_meta_pipeline_run_id"] if rows else None,
        "run_status": "success",
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_keys": META_SOURCE_KEY,
        "destination_key": DESTINATION_KEY,
        "input_row_count": player_table.num_rows,
        "output_row_count": len(rows),
        "warning_count": 0,
        "error_count": 0,
        "warning_reason_counts": "{}",
        "error_reason_counts": "{}",
        "assist_context_source_method_counts": dict(sorted(assist_method_counts.items())),
        "rebound_context_source_method_counts": dict(sorted(rebound_method_counts.items())),
    }
    write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=rows[0]["_meta_pipeline_run_id"] if rows else "player_game_opportunity_context_empty",
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
