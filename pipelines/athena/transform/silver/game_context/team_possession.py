"""
Build a canonical silver team-game possession context table.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/boxscore_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet
  s3://nba-analytics-lakehouse-dev/silver/possessions/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/possessions_ot_fallback/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=<GAME_ID>.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/silver/team_game_possession_context.parquet
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
TEAM_SOURCE_KEY = pgpc.TEAM_SOURCE_KEY
SCHEDULE_SOURCE_KEY = pgpc.SCHEDULE_SOURCE_KEY
POSSESSIONS_PREFIX = pgpc.POSSESSIONS_PREFIX
POSSESSIONS_OT_FALLBACK_PREFIX = pgpc.POSSESSIONS_OT_FALLBACK_PREFIX
PLAYBYPLAY_PREFIX = pgpc.PLAYBYPLAY_PREFIX
DESTINATION_KEY = "silver/team_game_possession_context.parquet"
TABLE_NAME = "team_game_possession_context"
META_SOURCE_SYSTEM = (
    "silver_boxscore_team_game|silver_scheduleLeagueV2_1|silver_possessions|"
    "silver_possessions_ot_fallback|silver_playbyplay"
)
META_SOURCE_KEY = (
    "silver/boxscore_team_game.parquet|silver/scheduleLeagueV2_1.parquet|"
    "silver/possessions/|silver/possessions_ot_fallback/|silver/playbyplay/"
)
META_SCHEMA_VERSION = 1

TEAM_REQUIRED_COLUMNS = pgpc.TEAM_REQUIRED_COLUMNS
SCHEDULE_REQUIRED_COLUMNS = pgpc.SCHEDULE_REQUIRED_COLUMNS
POSSESSIONS_REQUIRED_COLUMNS = pgpc.POSSESSIONS_REQUIRED_COLUMNS
PLAYBYPLAY_REQUIRED_COLUMNS = pgpc.PLAYBYPLAY_REQUIRED_COLUMNS

TARGET_SCHEMA = pa.schema(
    [
        pa.field("game_id", pa.string()),
        pa.field("team_id", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("offensive_possessions", pa.float64()),
        pa.field("defensive_possessions", pa.float64()),
        pa.field("possessions_total", pa.float64()),
        pa.field("possession_source_method", pa.string()),
        pa.field("exact_possessions_count", pa.float64()),
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


def init_team_stats(team_ids: set[int], source_method: str) -> dict[int, dict[str, Any]]:
    return {
        team_id: {
            "offensive_possessions": 0.0,
            "defensive_possessions": 0.0,
            "possession_source_method": source_method,
            "exact_possessions_count": 0.0,
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
        for team_id in sorted(team_ids)
    }


def build_played_teams_by_game(team_table: pa.Table) -> dict[str, set[int]]:
    played_teams_by_game: dict[str, set[int]] = {}
    for row in team_table.to_pylist():
        game_id = pgpc.normalize_game_id(row.get("gameId"))
        team_id = pgpc.to_int_or_none(row.get("teamId"))
        if game_id is None or team_id is None:
            continue
        played_teams_by_game.setdefault(game_id, set()).add(team_id)
    return played_teams_by_game


def build_exact_or_ot_team_game_stats(
    possession_rows: list[dict[str, Any]] | None,
    played_teams: set[int],
    *,
    source_method: str,
) -> dict[int, dict[str, Any]] | None:
    counted_rows = [row for row in possession_rows or [] if pgpc.to_bool_or_none(row.get("countsAsPossession")) is True]
    if not counted_rows:
        return None

    stats = init_team_stats(played_teams, source_method)
    count_field = "exact_possessions_count" if source_method == "exact" else "ot_fallback_possessions_count"
    game_flag_field = "exact_game_flag" if source_method == "exact" else "ot_fallback_game_flag"

    for row in counted_rows:
        offense_team_id = pgpc.to_int_or_none(row.get("offenseTeamId"))
        defense_team_id = pgpc.to_int_or_none(row.get("defenseTeamId"))
        if offense_team_id is None or defense_team_id is None:
            return None
        if offense_team_id not in stats or defense_team_id not in stats:
            return None
        stats[offense_team_id]["offensive_possessions"] += 1.0
        stats[offense_team_id][count_field] += 1.0
        stats[defense_team_id]["defensive_possessions"] += 1.0
        stats[defense_team_id][count_field] += 1.0

    for team_stats in stats.values():
        team_stats[game_flag_field] = 1
    return stats


def build_event_estimated_team_game_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    played_teams: set[int],
) -> dict[int, dict[str, Any]] | None:
    if not playbyplay_rows:
        return None

    counted_rows = [row for row in playbyplay_rows if pgpc.to_bool_or_none(row.get("countAsPossession")) is True]
    if not counted_rows:
        return None

    stats = init_team_stats(played_teams, "event_estimated")
    for row in counted_rows:
        offense_team_id = pgpc.to_int_or_none(row.get("resolvedOffenseTeamId"))
        defense_team_id = pgpc.to_int_or_none(row.get("resolvedDefenseTeamId"))
        if offense_team_id is None or defense_team_id is None:
            return None
        if offense_team_id not in stats or defense_team_id not in stats:
            return None
        stats[offense_team_id]["offensive_possessions"] += 1.0
        stats[offense_team_id]["event_estimated_possessions_count"] += 1.0
        stats[defense_team_id]["defensive_possessions"] += 1.0
        stats[defense_team_id]["event_estimated_possessions_count"] += 1.0

    for team_stats in stats.values():
        team_stats["event_estimated_game_flag"] = 1
    return stats


def build_boxscore_estimated_team_game_stats(
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

        estimated_possessions = pgpc.team_possessions_estimate(team_row, opponent_row)
        team_stats = stats[team_id]
        team_stats["offensive_possessions"] = estimated_possessions
        team_stats["defensive_possessions"] = estimated_possessions
        team_stats["boxscore_estimated_possessions_count"] = estimated_possessions * 2.0
        team_stats["boxscore_estimated_game_flag"] = 1
    return stats


def build_missing_team_game_stats(played_teams: set[int]) -> dict[int, dict[str, Any]]:
    stats = init_team_stats(played_teams, "missing")
    for team_stats in stats.values():
        team_stats["missing_game_flag"] = 1
    return stats


def choose_game_stats(
    *,
    game_id: str,
    played_teams: set[int],
    team_context_map: dict[tuple[str, int], dict[str, Any]],
    exact_rows: list[dict[str, Any]] | None,
    ot_fallback_rows: list[dict[str, Any]] | None,
    playbyplay_rows: list[dict[str, Any]] | None,
) -> dict[int, dict[str, Any]]:
    exact_stats = build_exact_or_ot_team_game_stats(exact_rows, played_teams, source_method="exact")
    if exact_stats is not None:
        return exact_stats

    ot_fallback_stats = build_exact_or_ot_team_game_stats(ot_fallback_rows, played_teams, source_method="ot_fallback")
    if ot_fallback_stats is not None:
        return ot_fallback_stats

    event_stats = build_event_estimated_team_game_stats(playbyplay_rows, played_teams)
    if event_stats is not None:
        return event_stats

    boxscore_stats = build_boxscore_estimated_team_game_stats(played_teams, team_context_map, game_id=game_id)
    if boxscore_stats is not None:
        return boxscore_stats

    return build_missing_team_game_stats(played_teams)


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

    offensive_possessions = pgpc.to_float_or_none(stats.get("offensive_possessions")) or 0.0
    defensive_possessions = pgpc.to_float_or_none(stats.get("defensive_possessions")) or 0.0
    return {
        "game_id": game_id,
        "team_id": team_id,
        "season_year": season_year,
        "season_start_year": season_start_year,
        "season_type_code": season_type_code,
        "season_type": season_type,
        "offensive_possessions": offensive_possessions,
        "defensive_possessions": defensive_possessions,
        "possessions_total": offensive_possessions + defensive_possessions,
        "possession_source_method": pgpc.to_str_or_none(stats.get("possession_source_method")),
        "exact_possessions_count": pgpc.to_float_or_none(stats.get("exact_possessions_count")) or 0.0,
        "ot_fallback_possessions_count": pgpc.to_float_or_none(stats.get("ot_fallback_possessions_count")) or 0.0,
        "event_estimated_possessions_count": pgpc.to_float_or_none(stats.get("event_estimated_possessions_count")) or 0.0,
        "boxscore_estimated_possessions_count": pgpc.to_float_or_none(stats.get("boxscore_estimated_possessions_count")) or 0.0,
        "missing_possessions_count": pgpc.to_float_or_none(stats.get("missing_possessions_count")) or 0.0,
        "exact_game_flag": pgpc.to_int_or_none(stats.get("exact_game_flag")) or 0,
        "ot_fallback_game_flag": pgpc.to_int_or_none(stats.get("ot_fallback_game_flag")) or 0,
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
    team_context_map = pgpc.build_team_context_map(team_table)
    schedule_map = pgpc.build_schedule_map(schedule_table)

    possession_game_ids = pgpc.list_partition_game_ids(s3_client, POSSESSIONS_PREFIX)
    ot_fallback_game_ids = pgpc.list_partition_game_ids(s3_client, POSSESSIONS_OT_FALLBACK_PREFIX)
    playbyplay_game_ids = pgpc.list_partition_game_ids(s3_client, PLAYBYPLAY_PREFIX)

    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = (
        f"team_game_possession_context_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    )

    def _build_game_rows(game_id: str, played_teams: set[int]) -> list[dict[str, Any]]:
        exact_rows = pgpc.read_partition_rows(
            s3_client,
            prefix=POSSESSIONS_PREFIX,
            game_id=game_id,
            columns=POSSESSIONS_REQUIRED_COLUMNS,
            available_ids=possession_game_ids,
        )
        ot_fallback_rows = pgpc.read_partition_rows(
            s3_client,
            prefix=POSSESSIONS_OT_FALLBACK_PREFIX,
            game_id=game_id,
            columns=POSSESSIONS_REQUIRED_COLUMNS,
            available_ids=ot_fallback_game_ids,
        )
        playbyplay_rows = pgpc.read_partition_rows(
            s3_client,
            prefix=PLAYBYPLAY_PREFIX,
            game_id=game_id,
            columns=PLAYBYPLAY_REQUIRED_COLUMNS,
            available_ids=playbyplay_game_ids,
        )
        game_stats = choose_game_stats(
            game_id=game_id,
            played_teams=played_teams,
            team_context_map=team_context_map,
            exact_rows=exact_rows,
            ot_fallback_rows=ot_fallback_rows,
            playbyplay_rows=playbyplay_rows,
        )
        schedule_info = schedule_map.get(game_id)
        return [
            finalize_team_game_row(
                game_id=game_id,
                team_id=team_id,
                stats=game_stats[team_id],
                schedule_info=schedule_info,
                pipeline_run_id=pipeline_run_id,
                ingested_at_utc=ingested_at_utc,
            )
            for team_id in sorted(played_teams)
        ]

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
    rows = build_rows(s3_client=s3_client, team_table=team_table, schedule_table=schedule_table)
    write_rows(rows, s3_client)

    ingested_at_utc = datetime.now(timezone.utc)
    source_counts = Counter(row.get("possession_source_method") or "unknown" for row in rows)
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
        "possession_source_method_counts": dict(sorted(source_counts.items())),
    }
    write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=rows[0]["_meta_pipeline_run_id"] if rows else "team_game_possession_context_empty",
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
