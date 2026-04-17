"""Purpose: Register semantic_gold parquet outputs as Athena external tables.
Inputs: Semantic-gold table specs and their published parquet schemas.
Outputs: Athena tables named after semantic objects under the active database.
Next file: tests/semantic_gold/test_deploy_semantic_gold_tables.py validates the DDL contract.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.transform.gold.athena_view_helpers import AthenaClient, load_settings

from pipelines.athena.transform.gold.gold_transform_helpers import S3_BUCKET

from .contracts import SEMANTIC_GOLD_TABLE_SPECS, SemanticGoldTableSpec

load_dotenv(override=True)


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


def fetch_schema(spec: SemanticGoldTableSpec) -> pa.Schema:
    s3 = boto3.client("s3")
    payload = s3.get_object(Bucket=S3_BUCKET, Key=spec.data_key)["Body"].read()
    return pq.read_schema(io.BytesIO(payload))


def build_create_table_ddl(spec: SemanticGoldTableSpec, schema: pa.Schema) -> str:
    column_lines = [f"  `{field.name}` {athena_type_for_field(field)}" for field in schema]
    columns_sql = ",\n".join(column_lines)
    return f"""
CREATE EXTERNAL TABLE {spec.table_name} (
{columns_sql}
)
STORED AS PARQUET
LOCATION '{spec.table_location}'
"""


def deploy_semantic_gold_tables() -> None:
    settings = load_settings()
    athena_client = AthenaClient(settings)

    for spec in SEMANTIC_GOLD_TABLE_SPECS:
        schema = fetch_schema(spec)
        athena_client.execute(f"DROP TABLE IF EXISTS {spec.table_name}")
        athena_client.execute(build_create_table_ddl(spec, schema))
        print(f"Created or replaced external table: {settings.database}.{spec.table_name}")


def main() -> None:
    deploy_semantic_gold_tables()


if __name__ == "__main__":
    main()
