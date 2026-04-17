"""Register the Athena gold parquet outputs as explicit external tables."""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings
    from pipelines.athena.transform.gold.player_surface import PLAYER_SURFACE_TABLE_SPECS
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings
    from pipelines.athena.transform.gold.player_surface import PLAYER_SURFACE_TABLE_SPECS

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"


@dataclass(frozen=True)
class GoldTableSpec:
    table_name: str
    data_key: str
    table_location: str


TABLE_SPECS = [
    GoldTableSpec(
        table_name="dim_date",
        data_key="gold/dim_date/dim_date.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/dim_date/",
    ),
    GoldTableSpec(
        table_name="dim_game",
        data_key="gold/dim_game/dim_game.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/dim_game/",
    ),
    GoldTableSpec(
        table_name="dim_team",
        data_key="gold/dim_team/dim_team.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/dim_team/",
    ),
    GoldTableSpec(
        table_name="fct_player_game",
        data_key="gold/fct_player_game/fct_player_game.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/fct_player_game/",
    ),
    GoldTableSpec(
        table_name="fct_team_game",
        data_key="gold/fct_team_game/fct_team_game.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/fct_team_game/",
    ),
    GoldTableSpec(
        table_name="fct_player_game_shot_profile_standard",
        data_key=(
            "gold/fct_player_game_shot_profile_standard/"
            "fct_player_game_shot_profile_standard.parquet"
        ),
        table_location=f"s3://{S3_BUCKET}/gold/fct_player_game_shot_profile_standard/",
    ),
    GoldTableSpec(
        table_name="fct_player_game_shot_profile_source",
        data_key=(
            "gold/fct_player_game_shot_profile_source/"
            "fct_player_game_shot_profile_source.parquet"
        ),
        table_location=f"s3://{S3_BUCKET}/gold/fct_player_game_shot_profile_source/",
    ),
    GoldTableSpec(
        table_name="fct_player_game_shot_type_source",
        data_key=(
            "gold/fct_player_game_shot_type_source/"
            "fct_player_game_shot_type_source.parquet"
        ),
        table_location=f"s3://{S3_BUCKET}/gold/fct_player_game_shot_type_source/",
    ),
    GoldTableSpec(
        table_name="agg_player_season",
        data_key="gold/agg_player_season/agg_player_season.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/agg_player_season/",
    ),
    GoldTableSpec(
        table_name="agg_team_season",
        data_key="gold/agg_team_season/agg_team_season.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/agg_team_season/",
    ),
    GoldTableSpec(
        table_name="team_season_provenance_sidecar",
        data_key=(
            "gold/team_season_provenance_sidecar/"
            "team_season_provenance_sidecar.parquet"
        ),
        table_location=f"s3://{S3_BUCKET}/gold/team_season_provenance_sidecar/",
    ),
    GoldTableSpec(
        table_name="player_season_percentiles",
        data_key="gold/player_season_percentiles/player_season_percentiles.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/player_season_percentiles/",
    ),
    GoldTableSpec(
        table_name="team_season_percentiles",
        data_key="gold/team_season_percentiles/team_season_percentiles.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/team_season_percentiles/",
    ),
    GoldTableSpec(
        table_name="player_award_history",
        data_key="gold/player_award_history/player_award_history.parquet",
        table_location=f"s3://{S3_BUCKET}/gold/player_award_history/",
    ),
] + [
    GoldTableSpec(
        table_name=spec.table_name,
        data_key=spec.data_key,
        table_location=spec.table_location,
    )
    for spec in PLAYER_SURFACE_TABLE_SPECS
]


def athena_type_for_field(field: pa.Field) -> str:
    field_type = field.type
    if pa.types.is_boolean(field_type):
        return "boolean"
    if pa.types.is_string(field_type):
        return "string"
    if pa.types.is_int64(field_type):
        return "bigint"
    if pa.types.is_int32(field_type):
        return "integer"
    if pa.types.is_int16(field_type):
        return "smallint"
    if pa.types.is_int8(field_type):
        return "tinyint"
    if pa.types.is_float64(field_type):
        return "double"
    if pa.types.is_float32(field_type):
        return "float"
    if pa.types.is_date(field_type):
        return "date"
    if pa.types.is_timestamp(field_type):
        return "timestamp"
    raise ValueError(f"Unsupported PyArrow type for Athena DDL: {field.name} -> {field_type}")


def fetch_schema(spec: GoldTableSpec) -> pa.Schema:
    s3 = boto3.client("s3")
    payload = s3.get_object(Bucket=S3_BUCKET, Key=spec.data_key)["Body"].read()
    return pq.read_schema(io.BytesIO(payload))


def build_create_table_ddl(spec: GoldTableSpec, schema: pa.Schema) -> str:
    column_lines = [f"  `{field.name}` {athena_type_for_field(field)}" for field in schema]
    columns_sql = ",\n".join(column_lines)
    return f"""
CREATE EXTERNAL TABLE {spec.table_name} (
{columns_sql}
)
STORED AS PARQUET
LOCATION '{spec.table_location}'
"""


def deploy_gold_tables() -> None:
    settings = load_settings()
    athena_client = AthenaClient(settings)

    for spec in TABLE_SPECS:
        schema = fetch_schema(spec)
        athena_client.execute(f"DROP TABLE IF EXISTS {spec.table_name}")
        athena_client.execute(build_create_table_ddl(spec, schema))
        print(f"Created or replaced external table: {settings.database}.{spec.table_name}")


def main() -> None:
    deploy_gold_tables()


if __name__ == "__main__":
    main()
