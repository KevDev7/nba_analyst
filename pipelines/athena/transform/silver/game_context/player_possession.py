"""
Build a canonical silver player-game possession context table.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_player_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet
  s3://nba-analytics-lakehouse-dev/silver/possessions/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/possessions_ot_fallback/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/on_court_state/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=<GAME_ID>.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/silver/player_game_possession_context.parquet
"""

from __future__ import annotations

import io
import os
import re
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.silver.silver_pipeline_helpers import write_audit_artifacts
except ModuleNotFoundError:
    from silver_pipeline_helpers import write_audit_artifacts  # type: ignore[no-redef]

load_dotenv(override=True)
if os.getenv("AWS_PROFILE", "").strip() == "":
    os.environ.pop("AWS_PROFILE", None)
if os.getenv("AWS_DEFAULT_PROFILE", "").strip() == "":
    os.environ.pop("AWS_DEFAULT_PROFILE", None)

S3_BUCKET = "nba-analytics-lakehouse-dev"
PLAYER_SOURCE_KEY = "silver/boxscore_player_game.parquet"
TEAM_SOURCE_KEY = "silver/boxscore_team_game.parquet"
SCHEDULE_SOURCE_KEY = "silver/scheduleLeagueV2_1.parquet"
POSSESSIONS_PREFIX = "silver/possessions/"
POSSESSIONS_OT_FALLBACK_PREFIX = "silver/possessions_ot_fallback/"
ON_COURT_PREFIX = "silver/on_court_state/"
PLAYBYPLAY_PREFIX = "silver/playbyplay/"
DESTINATION_KEY = "silver/player_game_possession_context.parquet"
TABLE_NAME = "player_game_possession_context"
META_SOURCE_SYSTEM = (
    "silver_boxscore_player_game|silver_boxscore_team_game|silver_scheduleLeagueV2_1|"
    "silver_possessions|silver_possessions_ot_fallback|silver_on_court_state|silver_playbyplay"
)
META_SOURCE_KEY = (
    "silver/boxscore_player_game.parquet|silver/boxscore_team_game.parquet|"
    "silver/scheduleLeagueV2_1.parquet|silver/possessions/|silver/possessions_ot_fallback/|"
    "silver/on_court_state/|silver/playbyplay/"
)
META_SCHEMA_VERSION = 1

SEASON_TYPE_LABELS = {
    "001": "preseason",
    "002": "regular_season",
    "003": "all_star",
    "004": "playoffs",
    "005": "play_in",
    "006": "nba_cup_final",
}

_ISO_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?$"
)

PLAYER_REQUIRED_COLUMNS = [
    "gameId",
    "teamId",
    "personId",
    "played",
    "minutes",
    "minutesCalculated",
    "fieldGoalsAttempted",
    "freeThrowsAttempted",
    "turnovers",
]

TEAM_REQUIRED_COLUMNS = [
    "gameId",
    "teamId",
    "score",
    "pointsAgainst",
    "minutes",
    "minutesCalculated",
    "fieldGoalsAttempted",
    "freeThrowsAttempted",
    "reboundsOffensive",
    "turnovers",
    "turnoversTotal",
]

SCHEDULE_REQUIRED_COLUMNS = [
    "gameId",
    "seasonYear",
]

POSSESSIONS_REQUIRED_COLUMNS = [
    "gameId",
    "startOrderNumber",
    "endOrderNumber",
    "offenseTeamId",
    "defenseTeamId",
    "offenseHomeAway",
    "defenseHomeAway",
    "pointsScoredOnPossession",
    "countsAsPossession",
    "homeLineupId",
    "awayLineupId",
]

ON_COURT_REQUIRED_COLUMNS = [
    "gameId",
    "start_orderNumber",
    "end_orderNumber",
    "home_teamId",
    "away_teamId",
    "home_personIds",
    "away_personIds",
    "lineup_valid_flag",
]

PLAYBYPLAY_REQUIRED_COLUMNS = [
    "gameId",
    "actionNumber",
    "orderNumber",
    "teamId",
    "personId",
    "scoreHome",
    "scoreAway",
    "resolvedOffenseTeamId",
    "resolvedDefenseTeamId",
    "countAsPossession",
    "isMadeShot",
    "isFreeThrow",
    "isTurnover",
    "isRebound",
    "isDreb",
    "linkedShotActionNumber",
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
        pa.field("offensive_possessions", pa.float64()),
        pa.field("defensive_possessions", pa.float64()),
        pa.field("possessions_total", pa.float64()),
        pa.field("used_offensive_possessions", pa.float64()),
        pa.field("team_points_for_while_on_court", pa.float64()),
        pa.field("team_points_against_while_on_court", pa.float64()),
        pa.field("possession_source_method", pa.string()),
        pa.field("exact_possessions_count", pa.float64()),
        pa.field("recovered_from_on_court_count", pa.float64()),
        pa.field("ot_fallback_possessions_count", pa.float64()),
        pa.field("event_estimated_possessions_count", pa.float64()),
        pa.field("boxscore_estimated_possessions_count", pa.float64()),
        pa.field("missing_possessions_count", pa.float64()),
        pa.field("exact_game_flag", pa.int64()),
        pa.field("ot_fallback_game_flag", pa.int64()),
        pa.field("event_estimated_game_flag", pa.int64()),
        pa.field("boxscore_estimated_game_flag", pa.int64()),
        pa.field("missing_game_flag", pa.int64()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def null_if_empty(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_str_or_none(value: Any) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    return str(value).strip()


def to_int_or_none(value: Any) -> int | None:
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float_or_none(value: Any) -> float | None:
    value = null_if_empty(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool_or_none(value: Any) -> bool | None:
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "t"}:
            return True
        if lowered in {"false", "0", "no", "n", "f"}:
            return False
    return None


def normalize_game_id(value: Any) -> str | None:
    text = to_str_or_none(value)
    if text is None:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return text
    if len(digits) >= 10:
        return digits[-10:]
    return digits.zfill(10)


def season_type_code_from_game_id(value: Any) -> str | None:
    game_id = normalize_game_id(value)
    if game_id is None or len(game_id) < 3:
        return None
    return game_id[:3]


def season_type_label_from_code(value: Any) -> str | None:
    return SEASON_TYPE_LABELS.get(to_str_or_none(value) or "")


def season_start_year_from_label(value: Any) -> int | None:
    text = to_str_or_none(value)
    if text is None or len(text) < 4 or not text[:4].isdigit():
        return None
    return int(text[:4])


def season_start_year_from_game_id(value: Any) -> int | None:
    game_id = normalize_game_id(value)
    if game_id is None or len(game_id) < 5 or not game_id[3:5].isdigit():
        return None
    return 2000 + int(game_id[3:5])


def parse_iso_duration_seconds(value: Any) -> float | None:
    text = to_str_or_none(value)
    if text is None:
        return None
    match = _ISO_DURATION_RE.match(text)
    if match is None:
        return None
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return (hours * 3600.0) + (minutes * 60.0) + seconds


def normalize_player_ids(value: Any) -> list[int] | None:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    elif isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return None
    normalized = [to_int_or_none(item) for item in value]
    if any(item is None for item in normalized):
        return None
    player_ids = [int(item) for item in normalized if item is not None]
    if len(player_ids) != 5 or len(set(player_ids)) != 5:
        return None
    return player_ids


def players_from_lineup_id(lineup_id: Any) -> list[int] | None:
    lineup_text = to_str_or_none(lineup_id)
    if lineup_text is None:
        return None
    parts = lineup_text.split("-")
    return normalize_player_ids(parts)


def extract_game_id_from_partition_key(prefix: str, key: str) -> str | None:
    if not key.startswith(prefix):
        return None
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".parquet"):
        return None
    return normalize_game_id(filename[len("game_id=") : -len(".parquet")])


def read_root_parquet_table(s3_client, key: str, columns: list[str]) -> pa.Table:
    payload = s3_client.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
    return pq.read_table(io.BytesIO(payload), columns=columns)


def read_partition_rows(
    s3_client,
    *,
    prefix: str,
    game_id: str,
    columns: list[str],
    available_ids: set[str],
) -> list[dict[str, Any]] | None:
    if game_id not in available_ids:
        return None
    key = f"{prefix}game_id={game_id}.parquet"
    try:
        payload = s3_client.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
            return None
        raise
    return pq.read_table(io.BytesIO(payload), columns=columns).to_pylist()


def list_partition_game_ids(s3_client, prefix: str) -> set[str]:
    game_ids: set[str] = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            game_id = extract_game_id_from_partition_key(prefix, obj.get("Key", ""))
            if game_id is not None:
                game_ids.add(game_id)
    return game_ids


def build_playbyplay_lookup(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    for row in rows:
        action_number = to_int_or_none(row.get("actionNumber"))
        if action_number is not None:
            lookup[action_number] = row
    return lookup


def init_player_stats(person_ids: set[int], source_method: str) -> dict[int, dict[str, Any]]:
    return {
        person_id: {
            "offensive_possessions": 0.0,
            "defensive_possessions": 0.0,
            "used_offensive_possessions": 0.0,
            "team_points_for_while_on_court": 0.0,
            "team_points_against_while_on_court": 0.0,
            "possession_source_method": source_method,
            "exact_possessions_count": 0.0,
            "recovered_from_on_court_count": 0.0,
            "ot_fallback_possessions_count": 0.0,
            "event_estimated_possessions_count": 0.0,
            "boxscore_estimated_possessions_count": 0.0,
            "missing_possessions_count": 0.0,
            "exact_game_flag": 0,
            "ot_fallback_game_flag": 0,
            "event_estimated_game_flag": 0,
            "boxscore_estimated_game_flag": 0,
            "missing_game_flag": 0,
        }
        for person_id in sorted(person_ids)
    }


def build_schedule_map(schedule_table: pa.Table) -> dict[str, dict[str, Any]]:
    schedule_map: dict[str, dict[str, Any]] = {}
    for row in schedule_table.to_pylist():
        game_id = normalize_game_id(row.get("gameId"))
        season_year = to_str_or_none(row.get("seasonYear"))
        if game_id is None:
            continue
        season_start_year = season_start_year_from_label(season_year)
        season_type_code = season_type_code_from_game_id(game_id)
        schedule_map[game_id] = {
            "season_year": season_year,
            "season_start_year": season_start_year,
            "season_type_code": season_type_code,
            "season_type": season_type_label_from_code(season_type_code),
        }
    return schedule_map


def build_played_players_by_game(player_table: pa.Table) -> dict[str, dict[int, dict[str, Any]]]:
    rows_by_game: dict[str, dict[int, dict[str, Any]]] = {}
    for row in player_table.to_pylist():
        game_id = normalize_game_id(row.get("gameId"))
        person_id = to_int_or_none(row.get("personId"))
        team_id = to_int_or_none(row.get("teamId"))
        minutes_seconds = parse_iso_duration_seconds(row.get("minutesCalculated"))
        if minutes_seconds is None:
            minutes_seconds = parse_iso_duration_seconds(row.get("minutes"))
        played_flag = 1 if to_int_or_none(row.get("played")) == 1 or (minutes_seconds or 0.0) > 0 else 0
        if game_id is None or person_id is None or team_id is None or played_flag != 1:
            continue
        rows_by_game.setdefault(game_id, {})[person_id] = {
            "person_id": person_id,
            "team_id": team_id,
            "minutes_seconds_total": minutes_seconds or 0.0,
            "field_goals_attempted": to_int_or_none(row.get("fieldGoalsAttempted")) or 0,
            "free_throws_attempted": to_int_or_none(row.get("freeThrowsAttempted")) or 0,
            "turnovers_total": to_int_or_none(row.get("turnoversTotal")) or to_int_or_none(row.get("turnovers")) or 0,
        }
    return rows_by_game


def build_team_context_map(team_table: pa.Table) -> dict[tuple[str, int], dict[str, Any]]:
    context: dict[tuple[str, int], dict[str, Any]] = {}
    teams_by_game: dict[str, list[int]] = {}
    for row in team_table.to_pylist():
        game_id = normalize_game_id(row.get("gameId"))
        team_id = to_int_or_none(row.get("teamId"))
        if game_id is None or team_id is None:
            continue
        teams_by_game.setdefault(game_id, []).append(team_id)
        minutes_seconds = parse_iso_duration_seconds(row.get("minutesCalculated"))
        if minutes_seconds is None:
            minutes_seconds = parse_iso_duration_seconds(row.get("minutes"))
        context[(game_id, team_id)] = {
            "score": to_int_or_none(row.get("score")),
            "points_against": to_int_or_none(row.get("pointsAgainst")),
            "minutes_seconds_total": minutes_seconds,
            "field_goals_attempted": to_int_or_none(row.get("fieldGoalsAttempted")),
            "free_throws_attempted": to_int_or_none(row.get("freeThrowsAttempted")),
            "rebounds_offensive": to_int_or_none(row.get("reboundsOffensive")),
            "turnovers_total": to_int_or_none(row.get("turnoversTotal")) or to_int_or_none(row.get("turnovers")),
        }

    for game_id, team_ids in teams_by_game.items():
        unique_team_ids = sorted(set(team_ids))
        if len(unique_team_ids) != 2:
            continue
        first_id, second_id = unique_team_ids
        context[(game_id, first_id)]["opponent_team_id"] = second_id
        context[(game_id, second_id)]["opponent_team_id"] = first_id
    return context


def build_on_court_lookup(on_court_rows: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not on_court_rows:
        return None
    stints: list[dict[str, Any]] = []
    home_team_id = None
    away_team_id = None
    for row in on_court_rows:
        home_team_id = home_team_id or to_int_or_none(row.get("home_teamId"))
        away_team_id = away_team_id or to_int_or_none(row.get("away_teamId"))
        home_players = normalize_player_ids(row.get("home_personIds"))
        away_players = normalize_player_ids(row.get("away_personIds"))
        if home_players is None or away_players is None:
            continue
        stints.append(
            {
                "start_order": to_int_or_none(row.get("start_orderNumber")),
                "end_order": to_int_or_none(row.get("end_orderNumber")),
                "home_players": home_players,
                "away_players": away_players,
            }
        )
    if home_team_id is None or away_team_id is None or not stints:
        return None
    stints.sort(key=lambda row: ((row.get("start_order") or 0), (row.get("end_order") or 0)))
    return {
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "stints": stints,
    }


def resolve_stint_for_range(
    lookup: dict[str, Any] | None,
    *,
    start_order: int | None,
    end_order: int | None,
    probe_order: int | None = None,
) -> tuple[list[int], list[int]] | None:
    if lookup is None:
        return None
    for stint in lookup["stints"]:
        stint_start = stint.get("start_order")
        stint_end = stint.get("end_order")
        effective_start = start_order if start_order is not None else end_order if end_order is not None else probe_order
        effective_end = end_order if end_order is not None else start_order if start_order is not None else probe_order
        if effective_start is None and effective_end is None:
            continue
        if stint_start is not None and effective_end is not None and effective_end < stint_start:
            continue
        if stint_end is not None and effective_start is not None and effective_start > stint_end:
            continue
        return stint["home_players"], stint["away_players"]
    return None


def assign_possession(
    stats: dict[int, dict[str, Any]],
    *,
    offense_players: list[int],
    defense_players: list[int],
    points: float,
    method_count_field: str,
    recovered: bool = False,
) -> None:
    for person_id in offense_players:
        player_stats = stats.get(person_id)
        if player_stats is None:
            continue
        player_stats["offensive_possessions"] += 1.0
        player_stats["team_points_for_while_on_court"] += points
        player_stats[method_count_field] += 1.0
        if recovered:
            player_stats["recovered_from_on_court_count"] += 1.0
    for person_id in defense_players:
        player_stats = stats.get(person_id)
        if player_stats is None:
            continue
        player_stats["defensive_possessions"] += 1.0
        player_stats["team_points_against_while_on_court"] += points
        player_stats[method_count_field] += 1.0
        if recovered:
            player_stats["recovered_from_on_court_count"] += 1.0


def resolve_used_offensive_player_id(
    end_row: dict[str, Any] | None,
    playbyplay_lookup: dict[int, dict[str, Any]],
    *,
    offense_team_id: int | None,
) -> int | None:
    if end_row is None or offense_team_id is None:
        return None

    def _player_id_if_matching_team(row: dict[str, Any] | None) -> int | None:
        if row is None or to_int_or_none(row.get("teamId")) != offense_team_id:
            return None
        return to_int_or_none(row.get("personId"))

    if to_bool_or_none(end_row.get("isTurnover")) is True:
        return _player_id_if_matching_team(end_row)

    if to_bool_or_none(end_row.get("isMadeShot")) is True:
        return _player_id_if_matching_team(end_row)

    if to_bool_or_none(end_row.get("isFreeThrow")) is True:
        return _player_id_if_matching_team(end_row)

    if (
        to_bool_or_none(end_row.get("isRebound")) is True
        and to_bool_or_none(end_row.get("isDreb")) is True
    ):
        linked_shot_action_number = to_int_or_none(end_row.get("linkedShotActionNumber"))
        linked_shot_row = playbyplay_lookup.get(linked_shot_action_number or -1)
        return _player_id_if_matching_team(linked_shot_row)

    return None


def resolve_home_away_team_ids_from_possession_row(
    row: dict[str, Any],
    on_court_lookup: dict[str, Any] | None,
) -> tuple[int, int] | None:
    offense_team_id = to_int_or_none(row.get("offenseTeamId"))
    defense_team_id = to_int_or_none(row.get("defenseTeamId"))
    offense_home_away = to_str_or_none(row.get("offenseHomeAway"))
    defense_home_away = to_str_or_none(row.get("defenseHomeAway"))
    if offense_team_id is None or defense_team_id is None:
        return None
    if offense_home_away == "h":
        return offense_team_id, defense_team_id
    if offense_home_away == "v":
        return defense_team_id, offense_team_id
    if defense_home_away == "h":
        return defense_team_id, offense_team_id
    if defense_home_away == "v":
        return offense_team_id, defense_team_id
    if on_court_lookup is None:
        return None
    return on_court_lookup["home_team_id"], on_court_lookup["away_team_id"]


def resolve_lineups_for_possession_row(
    row: dict[str, Any],
    on_court_lookup: dict[str, Any] | None,
) -> tuple[list[int], list[int], bool] | None:
    home_players = players_from_lineup_id(row.get("homeLineupId"))
    away_players = players_from_lineup_id(row.get("awayLineupId"))
    recovered = False
    if home_players is None or away_players is None:
        recovered_lineups = resolve_stint_for_range(
            on_court_lookup,
            start_order=to_int_or_none(row.get("startOrderNumber")),
            end_order=to_int_or_none(row.get("endOrderNumber")),
        )
        if recovered_lineups is None:
            return None
        recovered_home_players, recovered_away_players = recovered_lineups
        if home_players is None:
            home_players = recovered_home_players
            recovered = True
        if away_players is None:
            away_players = recovered_away_players
            recovered = True
    if home_players is None or away_players is None:
        return None
    return home_players, away_players, recovered


def build_exact_or_ot_player_game_stats(
    possession_rows: list[dict[str, Any]] | None,
    on_court_rows: list[dict[str, Any]] | None,
    playbyplay_rows: list[dict[str, Any]] | None,
    played_players: dict[int, dict[str, Any]],
    *,
    source_method: str,
) -> dict[int, dict[str, Any]] | None:
    counted_rows = [row for row in possession_rows or [] if to_bool_or_none(row.get("countsAsPossession")) is True]
    if not counted_rows:
        return None
    on_court_lookup = build_on_court_lookup(on_court_rows)
    stats = init_player_stats(set(played_players), source_method)
    count_field = "exact_possessions_count" if source_method == "exact" else "ot_fallback_possessions_count"
    game_flag_field = "exact_game_flag" if source_method == "exact" else "ot_fallback_game_flag"
    playbyplay_lookup = build_playbyplay_lookup(playbyplay_rows or [])

    for row in counted_rows:
        resolved = resolve_lineups_for_possession_row(row, on_court_lookup)
        if resolved is None:
            return None
        home_players, away_players, recovered = resolved
        team_ids = resolve_home_away_team_ids_from_possession_row(row, on_court_lookup)
        if team_ids is None:
            return None
        home_team_id, away_team_id = team_ids
        offense_team_id = to_int_or_none(row.get("offenseTeamId"))
        defense_team_id = to_int_or_none(row.get("defenseTeamId"))
        if offense_team_id == home_team_id and defense_team_id == away_team_id:
            offense_players = home_players
            defense_players = away_players
        elif offense_team_id == away_team_id and defense_team_id == home_team_id:
            offense_players = away_players
            defense_players = home_players
        else:
            return None
        assign_possession(
            stats,
            offense_players=offense_players,
            defense_players=defense_players,
            points=float(to_int_or_none(row.get("pointsScoredOnPossession")) or 0),
            method_count_field=count_field,
            recovered=recovered,
        )
        used_person_id = resolve_used_offensive_player_id(
            playbyplay_lookup.get(to_int_or_none(row.get("endActionNumber")) or -1),
            playbyplay_lookup,
            offense_team_id=offense_team_id,
        )
        if used_person_id is not None and used_person_id in stats:
            stats[used_person_id]["used_offensive_possessions"] += 1.0

    for player_stats in stats.values():
        player_stats[game_flag_field] = 1
    return stats


def build_event_estimated_player_game_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    on_court_rows: list[dict[str, Any]] | None,
    played_players: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]] | None:
    if not playbyplay_rows or not on_court_rows:
        return None
    on_court_lookup = build_on_court_lookup(on_court_rows)
    if on_court_lookup is None:
        return None
    counted_rows = [row for row in playbyplay_rows if to_bool_or_none(row.get("countAsPossession")) is True]
    if not counted_rows:
        return None

    stats = init_player_stats(set(played_players), "event_estimated")
    playbyplay_lookup = build_playbyplay_lookup(playbyplay_rows)
    previous_score_home = 0
    previous_score_away = 0

    for row in sorted(
        playbyplay_rows,
        key=lambda item: (
            to_int_or_none(item.get("orderNumber")) or 0,
            to_int_or_none(item.get("actionNumber")) or 0,
        ),
    ):
        order_number = to_int_or_none(row.get("orderNumber"))
        current_lineups = resolve_stint_for_range(
            on_court_lookup,
            start_order=order_number,
            end_order=order_number,
            probe_order=order_number,
        )
        score_home = to_int_or_none(row.get("scoreHome"))
        score_away = to_int_or_none(row.get("scoreAway"))
        effective_home = score_home if score_home is not None else previous_score_home
        effective_away = score_away if score_away is not None else previous_score_away
        delta_home = max(effective_home - previous_score_home, 0)
        delta_away = max(effective_away - previous_score_away, 0)
        previous_score_home = effective_home
        previous_score_away = effective_away

        if (delta_home > 0 or delta_away > 0) and current_lineups is not None:
            home_players, away_players = current_lineups
            for person_id in home_players:
                player_stats = stats.get(person_id)
                if player_stats is None:
                    continue
                player_stats["team_points_for_while_on_court"] += float(delta_home)
                player_stats["team_points_against_while_on_court"] += float(delta_away)
            for person_id in away_players:
                player_stats = stats.get(person_id)
                if player_stats is None:
                    continue
                player_stats["team_points_for_while_on_court"] += float(delta_away)
                player_stats["team_points_against_while_on_court"] += float(delta_home)

        if to_bool_or_none(row.get("countAsPossession")) is not True:
            continue
        if current_lineups is None:
            return None
        offense_team_id = to_int_or_none(row.get("resolvedOffenseTeamId"))
        defense_team_id = to_int_or_none(row.get("resolvedDefenseTeamId"))
        if offense_team_id is None or defense_team_id is None:
            return None
        home_team_id = on_court_lookup["home_team_id"]
        away_team_id = on_court_lookup["away_team_id"]
        home_players, away_players = current_lineups
        if offense_team_id == home_team_id and defense_team_id == away_team_id:
            offense_players = home_players
            defense_players = away_players
        elif offense_team_id == away_team_id and defense_team_id == home_team_id:
            offense_players = away_players
            defense_players = home_players
        else:
            return None
        assign_possession(
            stats,
            offense_players=offense_players,
            defense_players=defense_players,
            points=0.0,
            method_count_field="event_estimated_possessions_count",
        )
        used_person_id = resolve_used_offensive_player_id(
            row,
            playbyplay_lookup,
            offense_team_id=offense_team_id,
        )
        if used_person_id is not None and used_person_id in stats:
            stats[used_person_id]["used_offensive_possessions"] += 1.0

    for player_stats in stats.values():
        player_stats["event_estimated_game_flag"] = 1
    return stats


def team_possessions_estimate(team_row: dict[str, Any], opponent_row: dict[str, Any]) -> float:
    return 0.5 * (
        (
            float(to_int_or_none(team_row.get("field_goals_attempted")) or 0)
            + (0.44 * float(to_int_or_none(team_row.get("free_throws_attempted")) or 0))
            - float(to_int_or_none(team_row.get("rebounds_offensive")) or 0)
            + float(to_int_or_none(team_row.get("turnovers_total")) or 0)
        )
        + (
            float(to_int_or_none(opponent_row.get("field_goals_attempted")) or 0)
            + (0.44 * float(to_int_or_none(opponent_row.get("free_throws_attempted")) or 0))
            - float(to_int_or_none(opponent_row.get("rebounds_offensive")) or 0)
            + float(to_int_or_none(opponent_row.get("turnovers_total")) or 0)
        )
    )


def build_boxscore_estimated_player_game_stats(
    played_players: dict[int, dict[str, Any]],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    *,
    game_id: str,
) -> dict[int, dict[str, Any]] | None:
    if not played_players:
        return None
    stats = init_player_stats(set(played_players), "boxscore_estimated")
    for person_id, player_info in played_players.items():
        team_id = to_int_or_none(player_info.get("team_id"))
        if team_id is None:
            return None
        team_row = team_context_map.get((game_id, team_id))
        if team_row is None:
            return None
        opponent_team_id = to_int_or_none(team_row.get("opponent_team_id"))
        if opponent_team_id is None:
            return None
        opponent_row = team_context_map.get((game_id, opponent_team_id))
        if opponent_row is None:
            return None
        team_minutes_seconds_total = to_float_or_none(team_row.get("minutes_seconds_total"))
        player_minutes_seconds_total = to_float_or_none(player_info.get("minutes_seconds_total")) or 0.0
        if team_minutes_seconds_total is None or team_minutes_seconds_total <= 0:
            return None
        minute_share = player_minutes_seconds_total / (team_minutes_seconds_total / 5.0)
        estimated_possessions = minute_share * team_possessions_estimate(team_row, opponent_row)
        used_offensive_possessions = (
            float(to_int_or_none(player_info.get("field_goals_attempted")) or 0)
            + (0.44 * float(to_int_or_none(player_info.get("free_throws_attempted")) or 0))
            + float(to_int_or_none(player_info.get("turnovers_total")) or 0)
        )
        player_stats = stats[person_id]
        player_stats["offensive_possessions"] = estimated_possessions
        player_stats["defensive_possessions"] = estimated_possessions
        player_stats["used_offensive_possessions"] = used_offensive_possessions
        player_stats["team_points_for_while_on_court"] = minute_share * float(to_int_or_none(team_row.get("score")) or 0)
        player_stats["team_points_against_while_on_court"] = minute_share * float(
            to_int_or_none(team_row.get("points_against")) or 0
        )
        player_stats["boxscore_estimated_possessions_count"] = estimated_possessions * 2.0
        player_stats["boxscore_estimated_game_flag"] = 1
    return stats


def build_missing_player_game_stats(played_players: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    stats = init_player_stats(set(played_players), "missing")
    for player_stats in stats.values():
        player_stats["missing_game_flag"] = 1
    return stats


def choose_game_stats(
    *,
    game_id: str,
    played_players: dict[int, dict[str, Any]],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    exact_rows: list[dict[str, Any]] | None,
    ot_fallback_rows: list[dict[str, Any]] | None,
    on_court_rows: list[dict[str, Any]] | None,
    playbyplay_rows: list[dict[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    exact_stats = build_exact_or_ot_player_game_stats(
        exact_rows,
        on_court_rows,
        playbyplay_rows,
        played_players,
        source_method="exact",
    )
    if exact_stats is not None:
        return exact_stats
    ot_fallback_stats = build_exact_or_ot_player_game_stats(
        ot_fallback_rows,
        on_court_rows,
        playbyplay_rows,
        played_players,
        source_method="ot_fallback",
    )
    if ot_fallback_stats is not None:
        return ot_fallback_stats
    event_stats = build_event_estimated_player_game_stats(
        playbyplay_rows,
        on_court_rows,
        played_players,
    )
    if event_stats is not None:
        return event_stats
    boxscore_stats = build_boxscore_estimated_player_game_stats(
        played_players,
        team_context_map,
        game_id=game_id,
    )
    if boxscore_stats is not None:
        return boxscore_stats
    return build_missing_player_game_stats(played_players)


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
    season_year = to_str_or_none((schedule_info or {}).get("season_year"))
    season_start_year = to_int_or_none((schedule_info or {}).get("season_start_year"))
    season_type_code = to_str_or_none((schedule_info or {}).get("season_type_code")) or season_type_code_from_game_id(game_id)
    season_type = to_str_or_none((schedule_info or {}).get("season_type")) or season_type_label_from_code(season_type_code)
    if season_start_year is None:
        season_start_year = season_start_year_from_label(season_year) or season_start_year_from_game_id(game_id)
    if season_year is None and season_start_year is not None:
        season_year = f"{season_start_year}-{(season_start_year + 1) % 100:02d}"

    offensive_possessions = to_float_or_none(stats.get("offensive_possessions")) or 0.0
    defensive_possessions = to_float_or_none(stats.get("defensive_possessions")) or 0.0
    return {
        "game_id": game_id,
        "person_id": person_id,
        "team_id": team_id,
        "season_year": season_year,
        "season_start_year": season_start_year,
        "season_type_code": season_type_code,
        "season_type": season_type,
        "offensive_possessions": offensive_possessions,
        "defensive_possessions": defensive_possessions,
        "possessions_total": offensive_possessions + defensive_possessions,
        "used_offensive_possessions": to_float_or_none(stats.get("used_offensive_possessions")) or 0.0,
        "team_points_for_while_on_court": to_float_or_none(stats.get("team_points_for_while_on_court")) or 0.0,
        "team_points_against_while_on_court": to_float_or_none(stats.get("team_points_against_while_on_court")) or 0.0,
        "possession_source_method": to_str_or_none(stats.get("possession_source_method")),
        "exact_possessions_count": to_float_or_none(stats.get("exact_possessions_count")) or 0.0,
        "recovered_from_on_court_count": to_float_or_none(stats.get("recovered_from_on_court_count")) or 0.0,
        "ot_fallback_possessions_count": to_float_or_none(stats.get("ot_fallback_possessions_count")) or 0.0,
        "event_estimated_possessions_count": to_float_or_none(stats.get("event_estimated_possessions_count")) or 0.0,
        "boxscore_estimated_possessions_count": to_float_or_none(stats.get("boxscore_estimated_possessions_count")) or 0.0,
        "missing_possessions_count": to_float_or_none(stats.get("missing_possessions_count")) or 0.0,
        "exact_game_flag": to_int_or_none(stats.get("exact_game_flag")) or 0,
        "ot_fallback_game_flag": to_int_or_none(stats.get("ot_fallback_game_flag")) or 0,
        "event_estimated_game_flag": to_int_or_none(stats.get("event_estimated_game_flag")) or 0,
        "boxscore_estimated_game_flag": to_int_or_none(stats.get("boxscore_estimated_game_flag")) or 0,
        "missing_game_flag": to_int_or_none(stats.get("missing_game_flag")) or 0,
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
    schedule_map = build_schedule_map(schedule_table)

    possession_game_ids = list_partition_game_ids(s3_client, POSSESSIONS_PREFIX)
    ot_fallback_game_ids = list_partition_game_ids(s3_client, POSSESSIONS_OT_FALLBACK_PREFIX)
    on_court_game_ids = list_partition_game_ids(s3_client, ON_COURT_PREFIX)
    playbyplay_game_ids = list_partition_game_ids(s3_client, PLAYBYPLAY_PREFIX)

    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = (
        f"player_game_possession_context_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )

    def _build_game_rows(game_id: str, played_players: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        exact_rows = read_partition_rows(
            s3_client,
            prefix=POSSESSIONS_PREFIX,
            game_id=game_id,
            columns=POSSESSIONS_REQUIRED_COLUMNS,
            available_ids=possession_game_ids,
        )
        ot_fallback_rows = read_partition_rows(
            s3_client,
            prefix=POSSESSIONS_OT_FALLBACK_PREFIX,
            game_id=game_id,
            columns=POSSESSIONS_REQUIRED_COLUMNS,
            available_ids=ot_fallback_game_ids,
        )
        on_court_rows = read_partition_rows(
            s3_client,
            prefix=ON_COURT_PREFIX,
            game_id=game_id,
            columns=ON_COURT_REQUIRED_COLUMNS,
            available_ids=on_court_game_ids,
        )
        playbyplay_rows = read_partition_rows(
            s3_client,
            prefix=PLAYBYPLAY_PREFIX,
            game_id=game_id,
            columns=PLAYBYPLAY_REQUIRED_COLUMNS,
            available_ids=playbyplay_game_ids,
        )
        game_stats = choose_game_stats(
            game_id=game_id,
            played_players=played_players,
            team_context_map=team_context_map,
            exact_rows=exact_rows,
            ot_fallback_rows=ot_fallback_rows,
            on_court_rows=on_court_rows,
            playbyplay_rows=playbyplay_rows,
        )
        schedule_info = schedule_map.get(game_id)
        rows: list[dict[str, Any]] = []
        for person_id, player_info in sorted(played_players.items()):
            rows.append(
                finalize_player_game_row(
                    game_id=game_id,
                    person_id=person_id,
                    team_id=to_int_or_none(player_info.get("team_id")),
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
    player_table = read_root_parquet_table(s3_client, PLAYER_SOURCE_KEY, PLAYER_REQUIRED_COLUMNS)
    team_table = read_root_parquet_table(s3_client, TEAM_SOURCE_KEY, TEAM_REQUIRED_COLUMNS)
    schedule_table = read_root_parquet_table(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    rows = build_rows(
        s3_client=s3_client,
        player_table=player_table,
        team_table=team_table,
        schedule_table=schedule_table,
    )
    write_rows(rows, s3_client)

    ingested_at_utc = datetime.now(timezone.utc)
    warning_reason_counts = Counter(row.get("possession_source_method") or "unknown" for row in rows)
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
        "possession_source_method_counts": dict(sorted(warning_reason_counts.items())),
    }
    write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=rows[0]["_meta_pipeline_run_id"] if rows else "player_game_possession_context_empty",
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
