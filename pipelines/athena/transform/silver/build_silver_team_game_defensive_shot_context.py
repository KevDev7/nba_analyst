"""
Build a canonical silver team-game defensive shot context table.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet
  s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/pbpstats_event_context_v1/game_id=<GAME_ID>.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/silver/team_game_defensive_shot_context.parquet
"""

from __future__ import annotations

import io
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

S3_BUCKET = pgpc.S3_BUCKET
TEAM_SOURCE_KEY = "silver/boxscore_team_game.parquet"
SCHEDULE_SOURCE_KEY = pgpc.SCHEDULE_SOURCE_KEY
PLAYBYPLAY_PREFIX = pgpc.PLAYBYPLAY_PREFIX
EVENT_CONTEXT_PREFIX = "silver/pbpstats_event_context_v1/"
DESTINATION_KEY = "silver/team_game_defensive_shot_context.parquet"
TABLE_NAME = "team_game_defensive_shot_context"
META_SOURCE_SYSTEM = (
    "silver_boxscore_team_game|silver_scheduleLeagueV2_1|silver_playbyplay|"
    "silver_pbpstats_event_context_v1"
)
META_SOURCE_KEY = (
    "silver/boxscore_team_game.parquet|silver/scheduleLeagueV2_1.parquet|"
    "silver/playbyplay/|silver/pbpstats_event_context_v1/"
)
META_SCHEMA_VERSION = 1

TEAM_REQUIRED_COLUMNS = [
    "gameId",
    "teamId",
    "fieldGoalsAttempted",
    "threePointersAttempted",
]
SCHEDULE_REQUIRED_COLUMNS = pgpc.SCHEDULE_REQUIRED_COLUMNS
PLAYBYPLAY_REQUIRED_COLUMNS = [
    "gameId",
    "actionNumber",
    "resolvedOffenseTeamId",
    "resolvedDefenseTeamId",
    "isFieldGoal",
    "isMadeShot",
    "isMissedShot",
    "shotValue",
]
EVENT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "event_num",
    "home_team_id",
    "away_team_id",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("team_id", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("opponent_two_point_attempts", pa.float64()),
        pa.field("shot_context_source_method", pa.string()),
        pa.field("exact_two_point_attempts_count", pa.float64()),
        pa.field("event_estimated_two_point_attempts_count", pa.float64()),
        pa.field("boxscore_estimated_two_point_attempts_count", pa.float64()),
        pa.field("missing_two_point_attempts_count", pa.float64()),
        pa.field("exact_game_flag", pa.int64()),
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


def is_two_point_attempt(row: dict[str, Any]) -> bool:
    if pgpc.to_bool_or_none(row.get("isFieldGoal")) is not True:
        return False
    if pgpc.to_int_or_none(row.get("shotValue")) != 2:
        return False
    return (
        pgpc.to_bool_or_none(row.get("isMadeShot")) is True
        or pgpc.to_bool_or_none(row.get("isMissedShot")) is True
    )


def init_team_stats(team_ids: set[int], source_method: str) -> dict[int, dict[str, Any]]:
    return {
        team_id: {
            "opponent_two_point_attempts": 0.0,
            "shot_context_source_method": source_method,
            "exact_two_point_attempts_count": 0.0,
            "event_estimated_two_point_attempts_count": 0.0,
            "boxscore_estimated_two_point_attempts_count": 0.0,
            "missing_two_point_attempts_count": 0.0,
            "exact_game_flag": 0,
            "event_estimated_game_flag": 0,
            "boxscore_estimated_game_flag": 0,
            "missing_game_flag": 0,
        }
        for team_id in sorted(team_ids)
    }


def build_team_context_map(team_table: pa.Table) -> dict[tuple[str, int], dict[str, Any]]:
    context: dict[tuple[str, int], dict[str, Any]] = {}
    teams_by_game: dict[str, list[int]] = {}
    for row in team_table.to_pylist():
        game_id = pgpc.normalize_game_id(row.get("gameId"))
        team_id = pgpc.to_int_or_none(row.get("teamId"))
        if game_id is None or team_id is None:
            continue
        teams_by_game.setdefault(game_id, []).append(team_id)
        context[(game_id, team_id)] = {
            "field_goals_attempted": pgpc.to_int_or_none(row.get("fieldGoalsAttempted")),
            "three_pointers_attempted": pgpc.to_int_or_none(row.get("threePointersAttempted")),
        }

    for game_id, team_ids in teams_by_game.items():
        unique_team_ids = sorted(set(team_ids))
        if len(unique_team_ids) != 2:
            continue
        first_id, second_id = unique_team_ids
        context[(game_id, first_id)]["opponent_team_id"] = second_id
        context[(game_id, second_id)]["opponent_team_id"] = first_id
    return context


def build_played_teams_by_game(team_table: pa.Table) -> dict[str, set[int]]:
    played_teams_by_game: dict[str, set[int]] = {}
    for row in team_table.to_pylist():
        game_id = pgpc.normalize_game_id(row.get("gameId"))
        team_id = pgpc.to_int_or_none(row.get("teamId"))
        if game_id is None or team_id is None:
            continue
        played_teams_by_game.setdefault(game_id, set()).add(team_id)
    return played_teams_by_game


def build_event_context_by_event_num(
    event_context_rows: list[dict[str, Any]] | None,
) -> dict[int, tuple[int, int]]:
    context_by_event_num: dict[int, tuple[int, int]] = {}
    for row in event_context_rows or []:
        event_num = pgpc.to_int_or_none(row.get("event_num"))
        home_team_id = pgpc.to_int_or_none(row.get("home_team_id"))
        away_team_id = pgpc.to_int_or_none(row.get("away_team_id"))
        if event_num is None or home_team_id is None or away_team_id is None:
            continue
        context_by_event_num[event_num] = (home_team_id, away_team_id)
    return context_by_event_num


def infer_other_team_id(team_ids: tuple[int, int], known_team_id: int) -> int | None:
    first_id, second_id = team_ids
    if known_team_id == first_id:
        return second_id
    if known_team_id == second_id:
        return first_id
    return None


def build_exact_team_game_shot_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    played_teams: set[int],
) -> dict[int, dict[str, Any]] | None:
    shot_rows = [row for row in playbyplay_rows or [] if is_two_point_attempt(row)]
    if not shot_rows:
        return None

    stats = init_team_stats(played_teams, "exact")
    for row in shot_rows:
        defense_team_id = pgpc.to_int_or_none(row.get("resolvedDefenseTeamId"))
        if defense_team_id is None or defense_team_id not in stats:
            return None
        team_stats = stats[defense_team_id]
        team_stats["opponent_two_point_attempts"] += 1.0
        team_stats["exact_two_point_attempts_count"] += 1.0

    for team_stats in stats.values():
        team_stats["exact_game_flag"] = 1
    return stats


def build_event_estimated_team_game_shot_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
    played_teams: set[int],
) -> dict[int, dict[str, Any]] | None:
    shot_rows = [row for row in playbyplay_rows or [] if is_two_point_attempt(row)]
    if not shot_rows or not event_context_rows:
        return None

    context_by_event_num = build_event_context_by_event_num(event_context_rows)
    if not context_by_event_num:
        return None

    stats = init_team_stats(played_teams, "event_estimated")
    for row in shot_rows:
        action_number = pgpc.to_int_or_none(row.get("actionNumber"))
        team_ids = context_by_event_num.get(action_number or -1)
        if team_ids is None:
            return None

        defense_team_id = pgpc.to_int_or_none(row.get("resolvedDefenseTeamId"))
        if defense_team_id is None:
            offense_team_id = pgpc.to_int_or_none(row.get("resolvedOffenseTeamId"))
            if offense_team_id is None:
                return None
            defense_team_id = infer_other_team_id(team_ids, offense_team_id)
        if defense_team_id is None or defense_team_id not in stats:
            return None

        team_stats = stats[defense_team_id]
        team_stats["opponent_two_point_attempts"] += 1.0
        team_stats["event_estimated_two_point_attempts_count"] += 1.0

    for team_stats in stats.values():
        team_stats["event_estimated_game_flag"] = 1
    return stats


def build_boxscore_estimated_team_game_shot_stats(
    played_teams: set[int],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    *,
    game_id: str,
) -> dict[int, dict[str, Any]] | None:
    if not played_teams:
        return None

    stats = init_team_stats(played_teams, "boxscore_estimated")
    for team_id in played_teams:
        team_row = team_context_map.get((game_id, team_id))
        if team_row is None:
            return None
        opponent_team_id = pgpc.to_int_or_none(team_row.get("opponent_team_id"))
        if opponent_team_id is None:
            return None
        opponent_row = team_context_map.get((game_id, opponent_team_id))
        if opponent_row is None:
            return None

        opponent_fga = float(pgpc.to_int_or_none(opponent_row.get("field_goals_attempted")) or 0)
        opponent_three_pa = float(pgpc.to_int_or_none(opponent_row.get("three_pointers_attempted")) or 0)
        opponent_two_pa = max(opponent_fga - opponent_three_pa, 0.0)

        team_stats = stats[team_id]
        team_stats["opponent_two_point_attempts"] = opponent_two_pa
        team_stats["boxscore_estimated_two_point_attempts_count"] = opponent_two_pa
        team_stats["boxscore_estimated_game_flag"] = 1
    return stats


def build_missing_team_game_shot_stats(played_teams: set[int]) -> dict[int, dict[str, Any]]:
    stats = init_team_stats(played_teams, "missing")
    for team_stats in stats.values():
        team_stats["missing_game_flag"] = 1
    return stats


def choose_game_stats(
    *,
    game_id: str,
    played_teams: set[int],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    playbyplay_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    exact_stats = build_exact_team_game_shot_stats(playbyplay_rows, played_teams)
    if exact_stats is not None:
        return exact_stats

    event_stats = build_event_estimated_team_game_shot_stats(playbyplay_rows, event_context_rows, played_teams)
    if event_stats is not None:
        return event_stats

    boxscore_stats = build_boxscore_estimated_team_game_shot_stats(
        played_teams,
        team_context_map,
        game_id=game_id,
    )
    if boxscore_stats is not None:
        return boxscore_stats

    return build_missing_team_game_shot_stats(played_teams)


def finalize_team_game_row(
    *,
    game_id: str,
    team_id: int,
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
        "team_id": team_id,
        "season_year": season_year,
        "season_start_year": season_start_year,
        "season_type_code": season_type_code,
        "season_type": season_type,
        "opponent_two_point_attempts": pgpc.to_float_or_none(stats.get("opponent_two_point_attempts")) or 0.0,
        "shot_context_source_method": pgpc.to_str_or_none(stats.get("shot_context_source_method")),
        "exact_two_point_attempts_count": pgpc.to_float_or_none(stats.get("exact_two_point_attempts_count")) or 0.0,
        "event_estimated_two_point_attempts_count": pgpc.to_float_or_none(
            stats.get("event_estimated_two_point_attempts_count")
        )
        or 0.0,
        "boxscore_estimated_two_point_attempts_count": pgpc.to_float_or_none(
            stats.get("boxscore_estimated_two_point_attempts_count")
        )
        or 0.0,
        "missing_two_point_attempts_count": pgpc.to_float_or_none(stats.get("missing_two_point_attempts_count"))
        or 0.0,
        "exact_game_flag": pgpc.to_int_or_none(stats.get("exact_game_flag")) or 0,
        "event_estimated_game_flag": pgpc.to_int_or_none(stats.get("event_estimated_game_flag")) or 0,
        "boxscore_estimated_game_flag": pgpc.to_int_or_none(stats.get("boxscore_estimated_game_flag")) or 0,
        "missing_game_flag": pgpc.to_int_or_none(stats.get("missing_game_flag")) or 0,
        "_meta_pipeline_run_id": pipeline_run_id,
        "_meta_ingested_at_utc": ingested_at_utc,
        "_meta_source_system": META_SOURCE_SYSTEM,
        "_meta_source_key": META_SOURCE_KEY,
        "_meta_schema_version": META_SCHEMA_VERSION,
    }


def build_rows(
    *,
    s3_client,
    team_table: pa.Table,
    schedule_table: pa.Table,
) -> list[dict[str, Any]]:
    played_teams_by_game = build_played_teams_by_game(team_table)
    team_context_map = build_team_context_map(team_table)
    schedule_map = pgpc.build_schedule_map(schedule_table)

    playbyplay_game_ids = pgpc.list_partition_game_ids(s3_client, PLAYBYPLAY_PREFIX)
    event_context_game_ids = pgpc.list_partition_game_ids(s3_client, EVENT_CONTEXT_PREFIX)

    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = (
        f"team_game_defensive_shot_context_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )

    def _build_game_rows(game_id: str, played_teams: set[int]) -> list[dict[str, Any]]:
        playbyplay_rows = pgpc.read_partition_rows(
            s3_client,
            prefix=PLAYBYPLAY_PREFIX,
            game_id=game_id,
            columns=PLAYBYPLAY_REQUIRED_COLUMNS,
            available_ids=playbyplay_game_ids,
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
            played_teams=played_teams,
            team_context_map=team_context_map,
            playbyplay_rows=playbyplay_rows,
            event_context_rows=event_context_rows,
        )
        schedule_info = schedule_map.get(game_id)
        rows: list[dict[str, Any]] = []
        for team_id in sorted(played_teams):
            rows.append(
                finalize_team_game_row(
                    game_id=game_id,
                    team_id=team_id,
                    stats=game_stats[team_id],
                    schedule_info=schedule_info,
                    pipeline_run_id=pipeline_run_id,
                    ingested_at_utc=ingested_at_utc,
                )
            )
        return rows

    all_rows: list[dict[str, Any]] = []
    max_workers = min(16, max(1, len(played_teams_by_game)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_build_game_rows, game_id, played_teams): game_id
            for game_id, played_teams in sorted(played_teams_by_game.items())
        }
        for future in as_completed(future_map):
            all_rows.extend(future.result())

    all_rows.sort(
        key=lambda row: (
            row.get("game_id") or "",
            row.get("team_id") or -1,
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
    team_table = pgpc.read_root_parquet_table(s3_client, TEAM_SOURCE_KEY, TEAM_REQUIRED_COLUMNS)
    schedule_table = pgpc.read_root_parquet_table(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    rows = build_rows(
        s3_client=s3_client,
        team_table=team_table,
        schedule_table=schedule_table,
    )
    write_rows(rows, s3_client)

    ingested_at_utc = datetime.now(timezone.utc)
    source_method_counts = Counter(row.get("shot_context_source_method") or "unknown" for row in rows)
    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": rows[0]["_meta_pipeline_run_id"] if rows else None,
        "run_status": "success",
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_keys": META_SOURCE_KEY,
        "destination_key": DESTINATION_KEY,
        "input_row_count": team_table.num_rows,
        "output_row_count": len(rows),
        "warning_count": 0,
        "error_count": 0,
        "warning_reason_counts": "{}",
        "error_reason_counts": "{}",
        "shot_context_source_method_counts": dict(sorted(source_method_counts.items())),
    }
    write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=rows[0]["_meta_pipeline_run_id"] if rows else "team_game_defensive_shot_context_empty",
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
