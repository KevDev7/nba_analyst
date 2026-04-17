from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import boto3
import pytest
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass(frozen=True)
class AthenaTestSettings:
    database: str
    output_location: str
    region: str
    workgroup: str
    catalog: str
    timeout_seconds: float
    poll_interval_seconds: float

    @property
    def configured(self) -> bool:
        return bool(self.database and self.output_location and self.region)


class AthenaTestClient:
    def __init__(self, settings: AthenaTestSettings):
        self.settings = settings
        self.client = boto3.client("athena", region_name=settings.region)

    def execute(self, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
        try:
            start = self.client.start_query_execution(
                QueryString=sql,
                QueryExecutionContext={
                    "Database": self.settings.database,
                    "Catalog": self.settings.catalog,
                },
                ResultConfiguration={"OutputLocation": self.settings.output_location},
                WorkGroup=self.settings.workgroup,
            )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"Athena start_query_execution failed: {exc}") from exc

        query_execution_id = start["QueryExecutionId"]
        deadline = time.time() + self.settings.timeout_seconds
        while time.time() < deadline:
            execution = self.client.get_query_execution(QueryExecutionId=query_execution_id)
            state = execution["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                return self._fetch_all_results(query_execution_id)
            if state in {"FAILED", "CANCELLED"}:
                reason = execution["QueryExecution"]["Status"].get("StateChangeReason", "Athena query failed.")
                raise RuntimeError(f"Athena query failed: {reason}")
            time.sleep(self.settings.poll_interval_seconds)

        self.client.stop_query_execution(QueryExecutionId=query_execution_id)
        raise RuntimeError("Athena query timed out.")

    def _fetch_all_results(self, query_execution_id: str) -> tuple[list[str], list[dict[str, Any]]]:
        rows_payload: list[dict[str, Any]] = []
        metadata = None
        next_token = None

        while True:
            kwargs = {"QueryExecutionId": query_execution_id}
            if next_token:
                kwargs["NextToken"] = next_token
            result = self.client.get_query_results(**kwargs)
            metadata = metadata or result["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            rows_payload.extend(result["ResultSet"].get("Rows", []))
            next_token = result.get("NextToken")
            if not next_token:
                break

        if metadata is None:
            return [], []

        headers = [column["Name"] for column in metadata]
        parsed_rows: list[dict[str, Any]] = []
        for row in rows_payload[1:]:
            values = row.get("Data", [])
            parsed_row: dict[str, Any] = {}
            for index, header in enumerate(headers):
                raw = values[index].get("VarCharValue") if index < len(values) else None
                parsed_row[header] = self._coerce_value(raw, metadata[index]["Type"])
            parsed_rows.append(parsed_row)
        return headers, parsed_rows

    @staticmethod
    def _coerce_value(raw: str | None, athena_type: str) -> Any:
        if raw is None:
            return None
        lowered = athena_type.lower()
        if lowered.startswith(("integer", "bigint", "smallint", "tinyint")):
            return int(raw)
        if lowered.startswith(("double", "float", "real", "decimal")):
            return float(raw)
        if lowered.startswith("boolean"):
            return raw.lower() == "true"
        return raw


@pytest.fixture(scope="session")
def athena_settings() -> AthenaTestSettings:
    import os

    settings = AthenaTestSettings(
        database=os.getenv("ATHENA_DATABASE", "").strip(),
        output_location=os.getenv("ATHENA_OUTPUT_LOCATION", "").strip(),
        region=(os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION") or "").strip(),
        workgroup=os.getenv("ATHENA_WORKGROUP", "primary").strip() or "primary",
        catalog=os.getenv("ATHENA_CATALOG", "AwsDataCatalog").strip() or "AwsDataCatalog",
        timeout_seconds=float(os.getenv("ATHENA_TIMEOUT_SECONDS", "30")),
        poll_interval_seconds=float(os.getenv("ATHENA_POLL_INTERVAL_SECONDS", "0.5")),
    )
    if not settings.configured:
        pytest.skip("Athena test environment is not configured.")
    return settings


@pytest.fixture(scope="session")
def athena_client(athena_settings: AthenaTestSettings) -> AthenaTestClient:
    return AthenaTestClient(athena_settings)
