"""Shared helpers for Athena gold view deployment."""

from __future__ import annotations

import time
from dataclasses import dataclass

import boto3
from dotenv import load_dotenv

load_dotenv(override=True)


GOLD_SCHEMA = "gold"
SILVER_SCHEMA = "silver"
PLAYER_AGG_TABLE = "agg_player_season"
TEAM_AGG_TABLE = "agg_team_season"
PLAYER_SEASON_PERCENTILES_TABLE = "player_season_percentiles"
TEAM_SEASON_PERCENTILES_TABLE = "team_season_percentiles"
PLAYER_FACT_TABLE = "fct_player_game"
TEAM_FACT_TABLE = "fct_team_game"
PLAYER_GAME_SHOT_TYPE_SOURCE_TABLE = "fct_player_game_shot_type_source"
DIM_PLAYER_TABLE = "dim_player"
DIM_GAME_TABLE = "dim_game"
DIM_TEAM_TABLE = "dim_team"
SILVER_TEAM_TABLE = "boxscore_team_game"
SILVER_PLAYER_POSSESSION_CONTEXT_TABLE = "player_game_possession_context"
SILVER_PLAYER_DEFENSIVE_SHOT_CONTEXT_TABLE = "player_game_defensive_shot_context"
PLAYER_PROVENANCE_DEBUG_VIEW = "vw_player_season_provenance_debug"

CROSS_BACKEND_SUPPORTED_VIEW_NAMES = [
    "vw_team_season_boxscore_advanced",
]

ATHENA_ONLY_SUPPORTED_VIEW_NAMES = [
    "vw_player_season_boxscore_advanced",
    "vw_player_game_shot_type_source",
]

SUPPORTED_VIEW_NAMES = CROSS_BACKEND_SUPPORTED_VIEW_NAMES + ATHENA_ONLY_SUPPORTED_VIEW_NAMES

ATHENA_ONLY_INTERNAL_VIEW_NAMES = [
    PLAYER_PROVENANCE_DEBUG_VIEW,
]

DEFERRED_VIEW_NAMES = [
    "vw_player_season_pace",
    "vw_player_season_usage",
    "vw_player_season_per_possession",
    "vw_player_season_per_100_possessions",
]

RETIRED_VIEW_NAMES = [
    "vw_team_season_advanced",
    "vw_player_season_rebound_percentages",
    "vw_player_season_pie",
    "vw_player_season_per_minute",
    "vw_player_season_per_30_minutes",
    "vw_player_season_per_40_minutes",
    "vw_player_season_per_48_minutes",
    "vw_player_season_advanced_formulas",
    "vw_player_season_advanced",
]

NUMERIC_TYPES = (
    "integer",
    "bigint",
    "smallint",
    "tinyint",
    "double",
    "float",
    "real",
    "decimal",
)

INTERNAL_PLAYER_AGG_COLUMNS = [
    "agg_player_season_sk",
    "person_id",
    "current_player_sk",
    "season_year",
    "season_start_year",
    "raw_season_type_code",
    "season_type",
    "age_on_jan_31",
    "primary_team_id",
    "primary_team_abbreviation",
    "primary_team_name",
    "is_multi_team_season",
    "games_on_roster",
    "games_played",
    "games_started",
    "wins",
    "losses",
    "team_count",
    "seconds_played_total",
    "seconds_played_average",
    "minutes_per_game",
    "points_total",
    "assists_total",
    "rebounds_total",
    "steals_total",
    "blocks_total",
    "turnovers_total",
    "double_doubles",
    "triple_doubles",
    "quadruple_doubles",
    "field_goals_percentage",
    "three_pointers_percentage",
    "free_throws_percentage",
    "points_per_game",
    "assists_per_game",
    "rebounds_per_game",
    "rebounds_offensive_total",
    "rebounds_defensive_total",
    "field_goals_made_total",
    "field_goals_attempted_total",
    "three_pointers_made_total",
    "three_pointers_attempted_total",
    "free_throws_made_total",
    "free_throws_attempted_total",
    "points_fast_break_total",
    "points_in_the_paint_total",
    "points_second_chance_total",
    "fouls_offensive_total",
    "fouls_drawn_total",
    "fouls_personal_total",
    "fouls_technical_total",
    "raw_plus_value_total",
    "raw_minus_value_total",
    "plus_minus_points_total",
    "possessions_total",
    "record_source",
    "created_at_utc",
    "updated_at_utc",
]

PUBLIC_PLAYER_AGG_COLUMNS = [
    column_name
    for column_name in INTERNAL_PLAYER_AGG_COLUMNS
    if column_name != "raw_season_type_code"
]


def quote_ident(identifier: str) -> str:
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


@dataclass(frozen=True)
class AthenaSettings:
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


def load_settings() -> AthenaSettings:
    import os

    settings = AthenaSettings(
        database=os.getenv("ATHENA_DATABASE", "").strip(),
        output_location=os.getenv("ATHENA_OUTPUT_LOCATION", "").strip(),
        region=(os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION") or "").strip(),
        workgroup=os.getenv("ATHENA_WORKGROUP", "primary").strip() or "primary",
        catalog=os.getenv("ATHENA_CATALOG", "AwsDataCatalog").strip() or "AwsDataCatalog",
        timeout_seconds=float(os.getenv("ATHENA_TIMEOUT_SECONDS", "30")),
        poll_interval_seconds=float(os.getenv("ATHENA_POLL_INTERVAL_SECONDS", "0.5")),
    )
    if not settings.configured:
        raise RuntimeError("Athena environment is not configured. Check .env / AWS env vars.")
    return settings


class AthenaClient:
    def __init__(self, settings: AthenaSettings):
        self.settings = settings
        self.client = boto3.client("athena", region_name=settings.region)

    def execute(self, sql: str) -> tuple[list[str], list[dict[str, str | None]]]:
        start = self.client.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={
                "Database": self.settings.database,
                "Catalog": self.settings.catalog,
            },
            ResultConfiguration={"OutputLocation": self.settings.output_location},
            WorkGroup=self.settings.workgroup,
        )

        query_execution_id = start["QueryExecutionId"]
        deadline = time.time() + self.settings.timeout_seconds
        while time.time() < deadline:
            execution = self.client.get_query_execution(QueryExecutionId=query_execution_id)
            state = execution["QueryExecution"]["Status"]["State"]
            if state == "SUCCEEDED":
                return self._fetch_all_results(query_execution_id)
            if state in {"FAILED", "CANCELLED"}:
                reason = execution["QueryExecution"]["Status"].get("StateChangeReason", state)
                raise RuntimeError(f"Athena query failed: {reason}")
            time.sleep(self.settings.poll_interval_seconds)

        self.client.stop_query_execution(QueryExecutionId=query_execution_id)
        raise RuntimeError("Athena query timed out.")

    def _fetch_all_results(self, query_execution_id: str) -> tuple[list[str], list[dict[str, str | None]]]:
        rows_payload: list[dict[str, object]] = []
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
        parsed_rows: list[dict[str, str | None]] = []
        for row in rows_payload[1:]:
            values = row.get("Data", [])
            parsed_rows.append(
                {
                    headers[index]: values[index].get("VarCharValue") if index < len(values) else None
                    for index in range(len(headers))
                }
            )
        return headers, parsed_rows


def discover_table_columns(
    athena_client: AthenaClient,
    database: str,
    table_name: str,
) -> list[tuple[str, str]]:
    _, rows = athena_client.execute(
        f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = '{database}'
          AND table_name = '{table_name}'
        ORDER BY ordinal_position
        """
    )
    return [(row["column_name"] or "", row["data_type"] or "") for row in rows if row.get("column_name")]


def is_numeric_type(data_type: str) -> bool:
    lowered = data_type.lower()
    return lowered.startswith(NUMERIC_TYPES)


def discover_rate_source_columns(base_columns: list[tuple[str, str]]) -> list[str]:
    return [
        column_name
        for column_name, data_type in base_columns
        if column_name.endswith("_total")
        and column_name != "seconds_played_total"
        and is_numeric_type(data_type)
    ]


def rate_alias(source_column: str, suffix: str) -> str:
    return f"{source_column.removesuffix('_total')}_{suffix}"


def select_internal_player_agg_columns(base_columns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    column_map = {column_name: data_type for column_name, data_type in base_columns}
    missing = [column_name for column_name in INTERNAL_PLAYER_AGG_COLUMNS if column_name not in column_map]
    if missing:
        raise RuntimeError(
            "agg_player_season is missing required internal serving columns: "
            + ", ".join(missing)
        )
    return [(column_name, column_map[column_name]) for column_name in INTERNAL_PLAYER_AGG_COLUMNS]


def select_public_player_agg_columns(base_columns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    column_map = {column_name: data_type for column_name, data_type in base_columns}
    missing = [column_name for column_name in PUBLIC_PLAYER_AGG_COLUMNS if column_name not in column_map]
    if missing:
        raise RuntimeError(
            "agg_player_season is missing required public serving columns: "
            + ", ".join(missing)
        )
    return [(column_name, column_map[column_name]) for column_name in PUBLIC_PLAYER_AGG_COLUMNS]
