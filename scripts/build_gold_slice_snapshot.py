#!/usr/bin/env python3
# Purpose:
# Build the gold-first DuckDB snapshot used by the live semantic-layer slices.
#
# Uses:
# - Athena gold tables from the nba_analytics database
# - local DuckDB as the development snapshot target
#
# Produces:
# - fixtures/duckdb/gold_slice.duckdb with the live player/player-game snapshot
#
# Next:
# - future ontology/query/planning slices can point at this snapshot intentionally

from __future__ import annotations

import argparse
import csv
import os
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import boto3
import duckdb


ROOT = Path(__file__).resolve().parents[1]
DUCKDB_DIR = ROOT / "fixtures" / "duckdb"
DUCKDB_PATH = DUCKDB_DIR / "gold_slice.duckdb"

DEFAULT_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
DEFAULT_DATABASE = os.getenv("ATHENA_DATABASE", "nba_analytics")
DEFAULT_OUTPUT = os.getenv("ATHENA_OUTPUT_LOCATION", "s3://nba-analytics-lakehouse-dev/athena-results/")
DEFAULT_WORKGROUP = os.getenv("ATHENA_WORKGROUP", "primary")
DEFAULT_CATALOG = os.getenv("ATHENA_CATALOG", "AwsDataCatalog")
DEFAULT_SEASON_YEARS = ("2025-26", "2024-25")


PLAYER_QUERY_TEMPLATE = """
WITH current_players AS (
  SELECT DISTINCT person_id
  FROM dim_player
  WHERE is_current = 1
)
SELECT
  p.person_id,
  p.player_name,
  p.display_name,
  p.primary_position,
  p.latest_team_id,
  p.latest_nba_team_id
FROM dim_player p
JOIN current_players cp
  ON p.person_id = cp.person_id
WHERE p.is_current = 1
ORDER BY p.player_name ASC
"""

EXTENDED_PLAYER_QUERY_TEMPLATE = """
WITH current_players AS (
  SELECT DISTINCT person_id
  FROM dim_player
  WHERE is_current = 1
)
SELECT
  ep.person_id,
  ep.player_name_short,
  ep.latest_status,
  ep.position_group
FROM extended_player_dim ep
JOIN current_players cp
  ON ep.person_id = cp.person_id
ORDER BY ep.person_id ASC
"""

PLAYER_GAME_QUERY_TEMPLATE = """
WITH current_players AS (
  SELECT DISTINCT person_id
  FROM dim_player
  WHERE is_current = 1
)
SELECT
  CAST(game_id AS VARCHAR) || ':' || CAST(person_id AS VARCHAR) AS player_game_id,
  game_id,
  person_id,
  team_id,
  team,
  game_date,
  season_year,
  season_type,
  player_status,
  is_starter,
  minutes_played_decimal,
  points,
  assists,
  rebounds_total,
  steals,
  blocks,
  turnovers,
  field_goals_attempted,
  field_goals_made,
  three_pointers_attempted,
  three_pointers_made,
  free_throws_attempted,
  free_throws_made
FROM fct_player_game
WHERE person_id IN (SELECT person_id FROM current_players)
  AND season_year IN ({season_years})
  AND season_type = 'regular_season'
  AND did_play = 1
ORDER BY game_date DESC, person_id ASC
"""

PLAYER_SEASON_QUERY_TEMPLATE = """
WITH current_players AS (
  SELECT DISTINCT person_id
  FROM dim_player
  WHERE is_current = 1
)
SELECT
  person_id,
  season_year,
  season_type,
  games_played,
  minutes_per_game,
  points_per_game,
  assists_per_game,
  rebounds_per_game,
  points_total,
  assists_total,
  rebounds_total
FROM agg_player_season
WHERE person_id IN (SELECT person_id FROM current_players)
  AND season_year IN ({season_years})
  AND season_type = 'regular_season'
ORDER BY person_id ASC
"""


def run_athena_query(
    *,
    sql: str,
    region: str,
    database: str,
    output_location: str,
    workgroup: str,
    catalog: str,
) -> str:
    athena = boto3.client("athena", region_name=region)
    s3 = boto3.client("s3", region_name=region)
    query_execution_id = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database, "Catalog": catalog},
        ResultConfiguration={"OutputLocation": output_location},
        WorkGroup=workgroup,
    )["QueryExecutionId"]

    for _ in range(240):
        execution = athena.get_query_execution(QueryExecutionId=query_execution_id)
        state = execution["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            result_location = execution["QueryExecution"]["ResultConfiguration"]["OutputLocation"]
            parsed = urlparse(result_location)
            body = s3.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))["Body"].read()
            return body.decode("utf-8")
        if state in {"FAILED", "CANCELLED"}:
            reason = execution["QueryExecution"]["Status"].get("StateChangeReason", state)
            raise RuntimeError(f"Athena query failed: {reason}")
        time.sleep(0.5)
    raise TimeoutError("Athena query timed out.")


def write_csv(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def count_csv_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        return sum(1 for _ in reader)


def build_snapshot(
    *,
    season_years: tuple[str, ...],
    region: str,
    database: str,
    output_location: str,
    workgroup: str,
    catalog: str,
    force: bool,
) -> Path:
    DUCKDB_DIR.mkdir(parents=True, exist_ok=True)
    if DUCKDB_PATH.exists() and not force:
        return DUCKDB_PATH

    with tempfile.TemporaryDirectory(prefix="gold-slice-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        sources = {
            "player": PLAYER_QUERY_TEMPLATE,
            "extended_player": EXTENDED_PLAYER_QUERY_TEMPLATE,
            "player_game": PLAYER_GAME_QUERY_TEMPLATE.format(
                season_years=", ".join(f"'{season_year}'" for season_year in season_years)
            ),
            "player_season": PLAYER_SEASON_QUERY_TEMPLATE.format(
                season_years=", ".join(f"'{season_year}'" for season_year in season_years)
            ),
        }

        csv_paths: dict[str, Path] = {}
        row_counts: dict[str, int] = {}
        for table_name, sql in sources.items():
            csv_text = run_athena_query(
                sql=sql,
                region=region,
                database=database,
                output_location=output_location,
                workgroup=workgroup,
                catalog=catalog,
            )
            csv_path = temp_dir / f"{table_name}.csv"
            write_csv(csv_path, csv_text)
            csv_paths[table_name] = csv_path
            row_counts[table_name] = count_csv_rows(csv_path)

        db_path = DUCKDB_PATH
        if db_path.exists():
            db_path.unlink()
        conn = duckdb.connect(str(db_path))
        try:
            for table_name, csv_path in csv_paths.items():
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                conn.execute(
                    f'CREATE TABLE "{table_name}" AS SELECT * FROM read_csv_auto(?, HEADER=TRUE)',
                    [str(csv_path)],
                )
            conn.execute("DROP TABLE IF EXISTS snapshot_meta")
            conn.execute(
                """
                CREATE TABLE snapshot_meta AS
                SELECT
                  ? AS snapshot_id,
                  ? AS source_database,
                  ? AS source_season_years,
                  ? AS source_backend,
                  CURRENT_TIMESTAMP AS built_at_utc
                """,
                [uuid.uuid4().hex, database, ", ".join(season_years), "athena"],
            )
        finally:
            conn.close()

        print(f"Built snapshot at {db_path}")
        for table_name, row_count in row_counts.items():
            print(f"{table_name}: {row_count} rows")
        return db_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a compact gold-derived DuckDB snapshot from Athena.")
    parser.add_argument("--season-year", action="append", dest="season_years")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--output-location", default=DEFAULT_OUTPUT)
    parser.add_argument("--workgroup", default=DEFAULT_WORKGROUP)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    build_snapshot(
        season_years=tuple(args.season_years or DEFAULT_SEASON_YEARS),
        region=args.region,
        database=args.database,
        output_location=args.output_location,
        workgroup=args.workgroup,
        catalog=args.catalog,
        force=args.force,
    )


if __name__ == "__main__":
    main()
