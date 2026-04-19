"""
Build gold player_season_percentiles from canonical player season aggregates.

Reads:
  s3://nba-analytics-lakehouse-dev/legacy_gold/agg_player_season/agg_player_season.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_player/dim_player.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_player_game/fct_player_game.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_team_game/fct_team_game.parquet
  s3://nba-analytics-lakehouse-dev/silver/player_game_possession_context.parquet
  s3://nba-analytics-lakehouse-dev/silver/player_game_defensive_shot_context.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/legacy_gold/player_season_percentiles/player_season_percentiles.parquet
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import boto3
import duckdb
import pyarrow as pa
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold import deploy_player_season_provenance_debug_view as player_provenance_view
    from pipelines.athena.transform.gold.gold_transform_helpers import (
        S3_BUCKET,
        read_parquet_table_from_s3,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
    from pipelines.athena.transform.gold.season_percentile_helpers import (
        PercentileMetricSpec,
        attach_percentiles,
        register_arrow_table,
    )
    from pipelines.athena.transform.gold.transform_to_agg_player_season_parquet import TARGET_SCHEMA as PLAYER_AGG_SCHEMA
    from pipelines.athena.transform.gold.transform_to_fct_player_game_parquet import TARGET_SCHEMA as PLAYER_FACT_SCHEMA
    from pipelines.athena.transform.gold.transform_to_fct_team_game_parquet import TARGET_SCHEMA as TEAM_FACT_SCHEMA
except ImportError:
    import deploy_player_season_provenance_debug_view as player_provenance_view  # type: ignore[no-redef]
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        read_parquet_table_from_s3,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
    from season_percentile_helpers import PercentileMetricSpec, attach_percentiles, register_arrow_table  # type: ignore[no-redef]
    from transform_to_agg_player_season_parquet import TARGET_SCHEMA as PLAYER_AGG_SCHEMA  # type: ignore[no-redef]
    from transform_to_fct_player_game_parquet import TARGET_SCHEMA as PLAYER_FACT_SCHEMA  # type: ignore[no-redef]
    from transform_to_fct_team_game_parquet import TARGET_SCHEMA as TEAM_FACT_SCHEMA  # type: ignore[no-redef]

load_dotenv(override=True)

PLAYER_AGG_SOURCE_KEY = "legacy_gold/agg_player_season/agg_player_season.parquet"
DIM_PLAYER_SOURCE_KEY = "legacy_gold/dim_player/dim_player.parquet"
PLAYER_FACT_SOURCE_KEY = "legacy_gold/fct_player_game/fct_player_game.parquet"
TEAM_FACT_SOURCE_KEY = "legacy_gold/fct_team_game/fct_team_game.parquet"
PLAYER_POSSESSION_CONTEXT_SOURCE_KEY = "silver/player_game_possession_context.parquet"
PLAYER_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY = "silver/player_game_defensive_shot_context.parquet"
DESTINATION_KEY = "legacy_gold/player_season_percentiles/player_season_percentiles.parquet"

RECORD_SOURCE = "gold.agg_player_season|gold.vw_player_season_boxscore_advanced"

MIN_GAMES_PLAYED = 5
MIN_SECONDS_PLAYED_TOTAL = 100 * 60
MIN_FIELD_GOALS_ATTEMPTED_TOTAL = 25
MIN_THREE_POINTERS_ATTEMPTED_TOTAL = 10
MIN_FREE_THROWS_ATTEMPTED_TOTAL = 10
MIN_SCORING_ATTEMPTS_TOTAL = 25.0

DIM_PLAYER_REQUIRED_COLUMNS = [
    "player_sk",
    "display_name",
    "player_name",
    "is_current",
]

PLAYER_POSSESSION_CONTEXT_REQUIRED_COLUMNS = [
    "person_id",
    "season_year",
    "season_type_code",
    "exact_game_flag",
    "ot_fallback_game_flag",
    "event_estimated_game_flag",
    "boxscore_estimated_game_flag",
    "missing_game_flag",
    "offensive_possessions",
    "defensive_possessions",
    "team_points_for_while_on_court",
    "team_points_against_while_on_court",
]

PLAYER_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS = [
    "person_id",
    "season_year",
    "season_type_code",
    "exact_game_flag",
    "event_estimated_game_flag",
    "boxscore_estimated_game_flag",
    "missing_game_flag",
    "opponent_two_point_attempts_while_on_court",
]

PLAYER_PERCENTILE_SPECS = [
    PercentileMetricSpec(
        source_field="seconds_played_average",
        output_field="seconds_played_average_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row),
    ),
    PercentileMetricSpec(
        source_field="field_goals_percentage",
        output_field="field_goals_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row) and _has_min_attempts(row, "field_goals_attempted_total", MIN_FIELD_GOALS_ATTEMPTED_TOTAL),
    ),
    PercentileMetricSpec(
        source_field="three_pointers_percentage",
        output_field="three_pointers_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row)
        and _has_min_attempts(row, "three_pointers_attempted_total", MIN_THREE_POINTERS_ATTEMPTED_TOTAL),
    ),
    PercentileMetricSpec(
        source_field="free_throws_percentage",
        output_field="free_throws_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row) and _has_min_attempts(row, "free_throws_attempted_total", MIN_FREE_THROWS_ATTEMPTED_TOTAL),
    ),
    PercentileMetricSpec(
        source_field="points_per_game",
        output_field="points_per_game_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row),
    ),
    PercentileMetricSpec(
        source_field="assists_per_game",
        output_field="assists_per_game_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row),
    ),
    PercentileMetricSpec(
        source_field="rebounds_per_game",
        output_field="rebounds_per_game_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row),
    ),
    PercentileMetricSpec(
        source_field="minutes",
        output_field="minutes_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="offensive_rating",
        output_field="offensive_rating_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="defensive_rating",
        output_field="defensive_rating_percentile",
        direction="lower",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="net_rating",
        output_field="net_rating_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="assist_percentage",
        output_field="assist_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="ast_to_turnover_ratio",
        output_field="ast_to_turnover_ratio_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="assist_ratio",
        output_field="assist_ratio_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="offensive_rebound_percentage",
        output_field="offensive_rebound_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="defensive_rebound_percentage",
        output_field="defensive_rebound_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="rebound_percentage",
        output_field="rebound_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="turnover_ratio",
        output_field="turnover_ratio_percentile",
        direction="lower",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="effective_field_goal_percentage",
        output_field="effective_field_goal_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row) and _has_min_scoring_attempts(row),
    ),
    PercentileMetricSpec(
        source_field="three_point_attempt_rate",
        output_field="three_point_attempt_rate_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row) and _has_min_attempts(row, "field_goals_attempted_total", MIN_FIELD_GOALS_ATTEMPTED_TOTAL),
    ),
    PercentileMetricSpec(
        source_field="free_throw_attempt_rate",
        output_field="free_throw_attempt_rate_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row) and _has_min_attempts(row, "field_goals_attempted_total", MIN_FIELD_GOALS_ATTEMPTED_TOTAL),
    ),
    PercentileMetricSpec(
        source_field="true_shooting_percentage",
        output_field="true_shooting_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_games(row) and _has_min_scoring_attempts(row),
    ),
    PercentileMetricSpec(
        source_field="usage_percentage",
        output_field="usage_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="pace",
        output_field="pace_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="pie",
        output_field="pie_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="steal_percentage",
        output_field="steal_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
    PercentileMetricSpec(
        source_field="block_percentage",
        output_field="block_percentage_percentile",
        direction="higher",
        qualifies=lambda row: _has_min_minutes(row),
    ),
]

PLAYER_PERCENTILE_FIELDS = [spec.output_field for spec in PLAYER_PERCENTILE_SPECS]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("player_season_percentiles_sk", pa.int64()),
        pa.field("person_id", pa.int64()),
        pa.field("current_player_sk", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        *[pa.field(field_name, pa.int64()) for field_name in PLAYER_PERCENTILE_FIELDS],
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)


def _has_min_games(row: dict[str, Any]) -> bool:
    return (to_int_or_none(row.get("games_played")) or 0) >= MIN_GAMES_PLAYED


def _has_min_minutes(row: dict[str, Any]) -> bool:
    return _has_min_games(row) and (to_float_or_none(row.get("seconds_played_total")) or 0.0) >= MIN_SECONDS_PLAYED_TOTAL


def _has_min_attempts(row: dict[str, Any], field_name: str, minimum: int) -> bool:
    return (to_int_or_none(row.get(field_name)) or 0) >= minimum


def _has_min_scoring_attempts(row: dict[str, Any]) -> bool:
    field_goal_attempts = to_float_or_none(row.get("field_goals_attempted_total")) or 0.0
    free_throw_attempts = to_float_or_none(row.get("free_throws_attempted_total")) or 0.0
    return _has_min_games(row) and (field_goal_attempts + (0.44 * free_throw_attempts)) >= MIN_SCORING_ATTEMPTS_TOTAL


def _build_player_advanced_source_table(
    agg_player_table: pa.Table,
    dim_player_table: pa.Table,
    player_fact_table: pa.Table,
    team_fact_table: pa.Table,
    player_possession_context_table: pa.Table,
    player_defensive_shot_context_table: pa.Table,
) -> pa.Table:
    base_columns = [(column_name, "") for column_name in agg_player_table.schema.names]

    with duckdb.connect() as conn:
        register_arrow_table(conn, table_name="agg_player_season", table=agg_player_table)
        register_arrow_table(conn, table_name="dim_player", table=dim_player_table)
        register_arrow_table(conn, table_name="fct_player_game", table=player_fact_table)
        register_arrow_table(conn, table_name="fct_team_game", table=team_fact_table)
        register_arrow_table(conn, table_name="player_game_possession_context", table=player_possession_context_table)
        register_arrow_table(
            conn,
            table_name="player_game_defensive_shot_context",
            table=player_defensive_shot_context_table,
        )

        conn.execute(player_provenance_view.build_view_sql(player_provenance_view.VIEW_NAME, base_columns))

        return conn.execute(
            """
            WITH "played_player_games" AS (
                SELECT
                    "game_id",
                    "person_id",
                    "team_id",
                    "season_year",
                    "raw_season_type_code"
                FROM "fct_player_game"
                WHERE "person_id" IS NOT NULL
                  AND "team_id" IS NOT NULL
                  AND (
                      COALESCE("did_play", 0) = 1
                      OR COALESCE("seconds_played_total", 0) > 0
                  )
            ),
            "player_team_context" AS (
                SELECT
                    "ppg"."person_id",
                    "ppg"."season_year",
                    "ppg"."raw_season_type_code",
                    SUM(COALESCE("tg"."seconds_played_total", 0)) AS "team_seconds_played_total",
                    SUM(COALESCE("tg"."field_goals_made", 0)) AS "team_field_goals_made_total",
                    SUM(COALESCE("tg"."field_goals_attempted", 0)) AS "team_field_goals_attempted_total",
                    SUM(COALESCE("tg"."free_throws_attempted", 0)) AS "team_free_throws_attempted_total",
                    SUM(COALESCE("tg"."turnovers", 0)) AS "team_turnovers_total",
                    SUM(COALESCE("tg"."rebounds_offensive", 0)) AS "team_rebounds_offensive_total",
                    SUM(COALESCE("tg"."rebounds_defensive", 0)) AS "team_rebounds_defensive_total",
                    SUM(COALESCE("tg"."rebounds_total", 0)) AS "team_rebounds_total",
                    SUM(COALESCE("opp"."rebounds_offensive", 0)) AS "opponent_rebounds_offensive_total",
                    SUM(COALESCE("opp"."rebounds_defensive", 0)) AS "opponent_rebounds_defensive_total",
                    SUM(COALESCE("opp"."rebounds_total", 0)) AS "opponent_rebounds_total"
                FROM "played_player_games" AS "ppg"
                INNER JOIN "fct_team_game" AS "tg"
                    ON "ppg"."game_id" = "tg"."game_id"
                   AND "ppg"."team_id" = "tg"."team_id"
                INNER JOIN "fct_team_game" AS "opp"
                    ON "ppg"."game_id" = "opp"."game_id"
                   AND "tg"."opponent_team_id" = "opp"."team_id"
                GROUP BY 1, 2, 3
            ),
            "pie_game_totals" AS (
                SELECT
                    "game_id",
                    SUM(COALESCE("points", 0)) AS "game_points_total",
                    SUM(COALESCE("field_goals_made", 0)) AS "game_field_goals_made_total",
                    SUM(COALESCE("free_throws_made", 0)) AS "game_free_throws_made_total",
                    SUM(COALESCE("field_goals_attempted", 0)) AS "game_field_goals_attempted_total",
                    SUM(COALESCE("free_throws_attempted", 0)) AS "game_free_throws_attempted_total",
                    SUM(COALESCE("rebounds_defensive", 0)) AS "game_rebounds_defensive_total",
                    SUM(COALESCE("rebounds_offensive", 0)) AS "game_rebounds_offensive_total",
                    SUM(COALESCE("assists", 0)) AS "game_assists_total",
                    SUM(COALESCE("steals", 0)) AS "game_steals_total",
                    SUM(COALESCE("blocks", 0)) AS "game_blocks_total",
                    SUM(COALESCE("fouls_personal", 0)) AS "game_fouls_personal_total",
                    SUM(COALESCE("turnovers", 0)) AS "game_turnovers_total"
                FROM "fct_player_game"
                GROUP BY 1
            ),
            "player_pie_context" AS (
                SELECT
                    "ppg"."person_id",
                    "ppg"."season_year",
                    "ppg"."raw_season_type_code",
                    SUM(
                        CAST("pgt"."game_points_total" AS double)
                        + CAST("pgt"."game_field_goals_made_total" AS double)
                        + CAST("pgt"."game_free_throws_made_total" AS double)
                        - CAST("pgt"."game_field_goals_attempted_total" AS double)
                        - CAST("pgt"."game_free_throws_attempted_total" AS double)
                        + CAST("pgt"."game_rebounds_defensive_total" AS double)
                        + (0.5 * CAST("pgt"."game_rebounds_offensive_total" AS double))
                        + CAST("pgt"."game_assists_total" AS double)
                        + CAST("pgt"."game_steals_total" AS double)
                        + (0.5 * CAST("pgt"."game_blocks_total" AS double))
                        - CAST("pgt"."game_fouls_personal_total" AS double)
                        - CAST("pgt"."game_turnovers_total" AS double)
                    ) AS "pie_denominator"
                FROM "played_player_games" AS "ppg"
                INNER JOIN "pie_game_totals" AS "pgt"
                    ON "ppg"."game_id" = "pgt"."game_id"
                GROUP BY 1, 2, 3
            )
            SELECT
                "aps"."person_id",
                "aps"."current_player_sk",
                "aps"."season_year",
                "aps"."season_start_year",
                "aps"."raw_season_type_code",
                "aps"."season_type",
                "aps"."games_played",
                "aps"."seconds_played_total",
                "aps"."field_goals_attempted_total",
                "aps"."three_pointers_attempted_total",
                "aps"."free_throws_attempted_total",
                "aps"."seconds_played_average",
                "aps"."field_goals_percentage",
                "aps"."three_pointers_percentage",
                "aps"."free_throws_percentage",
                "aps"."points_per_game",
                "aps"."assists_per_game",
                "aps"."rebounds_per_game",
                CAST("aps"."seconds_played_total" AS double) / 60.0 AS "minutes",
                CASE
                    WHEN COALESCE("prov"."offensive_possessions_total", 0) > 0
                    THEN ROUND(
                        100.0 * CAST("prov"."team_points_for_while_on_court_total" AS double)
                        / CAST("prov"."offensive_possessions_total" AS double),
                        1
                    )
                END AS "offensive_rating",
                CASE
                    WHEN COALESCE("prov"."defensive_possessions_total", 0) > 0
                    THEN ROUND(
                        100.0 * CAST("prov"."team_points_against_while_on_court_total" AS double)
                        / CAST("prov"."defensive_possessions_total" AS double),
                        1
                    )
                END AS "defensive_rating",
                CASE
                    WHEN COALESCE("prov"."offensive_possessions_total", 0) > 0
                     AND COALESCE("prov"."defensive_possessions_total", 0) > 0
                    THEN ROUND(
                        (
                            100.0 * CAST("prov"."team_points_for_while_on_court_total" AS double)
                            / CAST("prov"."offensive_possessions_total" AS double)
                        ) - (
                            100.0 * CAST("prov"."team_points_against_while_on_court_total" AS double)
                            / CAST("prov"."defensive_possessions_total" AS double)
                        ),
                        1
                    )
                END AS "net_rating",
                CASE
                    WHEN COALESCE("aps"."seconds_played_total", 0) > 0
                     AND COALESCE("ctx"."team_seconds_played_total", 0) > 0
                     AND (
                        ((CAST("aps"."seconds_played_total" AS double) / 60.0) / (CAST("ctx"."team_seconds_played_total" AS double) / 300.0))
                        * CAST("ctx"."team_field_goals_made_total" AS double)
                     ) - CAST("aps"."field_goals_made_total" AS double) <> 0
                    THEN ROUND(
                        100.0 * CAST("aps"."assists_total" AS double) / (
                            (
                                ((CAST("aps"."seconds_played_total" AS double) / 60.0) / (CAST("ctx"."team_seconds_played_total" AS double) / 300.0))
                                * CAST("ctx"."team_field_goals_made_total" AS double)
                            ) - CAST("aps"."field_goals_made_total" AS double)
                        ),
                        1
                    )
                END AS "assist_percentage",
                CASE
                    WHEN COALESCE("aps"."turnovers_total", 0) <> 0
                    THEN ROUND(CAST("aps"."assists_total" AS double) / CAST("aps"."turnovers_total" AS double), 2)
                END AS "ast_to_turnover_ratio",
                CASE
                    WHEN (
                        COALESCE("aps"."field_goals_attempted_total", 0)
                        + (0.44 * COALESCE("aps"."free_throws_attempted_total", 0))
                        + COALESCE("aps"."assists_total", 0)
                        + COALESCE("aps"."turnovers_total", 0)
                    ) <> 0
                    THEN ROUND(
                        100.0 * CAST("aps"."assists_total" AS double) / (
                            CAST("aps"."field_goals_attempted_total" AS double)
                            + (0.44 * CAST("aps"."free_throws_attempted_total" AS double))
                            + CAST("aps"."assists_total" AS double)
                            + CAST("aps"."turnovers_total" AS double)
                        ),
                        1
                    )
                END AS "assist_ratio",
                CASE
                    WHEN COALESCE("aps"."seconds_played_total", 0) > 0
                     AND COALESCE("ctx"."team_rebounds_offensive_total", 0) + COALESCE("ctx"."opponent_rebounds_defensive_total", 0) > 0
                    THEN ROUND(
                        CAST("aps"."rebounds_offensive_total" AS double)
                        * (CAST("ctx"."team_seconds_played_total" AS double) / 300.0)
                        * 100.0
                        / (
                            (CAST("aps"."seconds_played_total" AS double) / 60.0)
                            * (
                                CAST("ctx"."team_rebounds_offensive_total" AS double)
                                + CAST("ctx"."opponent_rebounds_defensive_total" AS double)
                            )
                        ),
                        1
                    )
                END AS "offensive_rebound_percentage",
                CASE
                    WHEN COALESCE("aps"."seconds_played_total", 0) > 0
                     AND COALESCE("ctx"."team_rebounds_defensive_total", 0) + COALESCE("ctx"."opponent_rebounds_offensive_total", 0) > 0
                    THEN ROUND(
                        CAST("aps"."rebounds_defensive_total" AS double)
                        * (CAST("ctx"."team_seconds_played_total" AS double) / 300.0)
                        * 100.0
                        / (
                            (CAST("aps"."seconds_played_total" AS double) / 60.0)
                            * (
                                CAST("ctx"."team_rebounds_defensive_total" AS double)
                                + CAST("ctx"."opponent_rebounds_offensive_total" AS double)
                            )
                        ),
                        1
                    )
                END AS "defensive_rebound_percentage",
                CASE
                    WHEN COALESCE("aps"."seconds_played_total", 0) > 0
                     AND COALESCE("ctx"."team_rebounds_total", 0) + COALESCE("ctx"."opponent_rebounds_total", 0) > 0
                    THEN ROUND(
                        CAST("aps"."rebounds_total" AS double)
                        * (CAST("ctx"."team_seconds_played_total" AS double) / 300.0)
                        * 100.0
                        / (
                            (CAST("aps"."seconds_played_total" AS double) / 60.0)
                            * (
                                CAST("ctx"."team_rebounds_total" AS double)
                                + CAST("ctx"."opponent_rebounds_total" AS double)
                            )
                        ),
                        1
                    )
                END AS "rebound_percentage",
                CASE
                    WHEN (
                        COALESCE("aps"."field_goals_attempted_total", 0)
                        + (0.44 * COALESCE("aps"."free_throws_attempted_total", 0))
                        + COALESCE("aps"."assists_total", 0)
                        + COALESCE("aps"."turnovers_total", 0)
                    ) <> 0
                    THEN ROUND(
                        100.0 * CAST("aps"."turnovers_total" AS double) / (
                            CAST("aps"."field_goals_attempted_total" AS double)
                            + (0.44 * CAST("aps"."free_throws_attempted_total" AS double))
                            + CAST("aps"."assists_total" AS double)
                            + CAST("aps"."turnovers_total" AS double)
                        ),
                        1
                    )
                END AS "turnover_ratio",
                CASE
                    WHEN COALESCE("aps"."field_goals_attempted_total", 0) <> 0
                    THEN ROUND(
                        100.0 * (
                            CAST("aps"."field_goals_made_total" AS double)
                            + (0.5 * CAST("aps"."three_pointers_made_total" AS double))
                        ) / CAST("aps"."field_goals_attempted_total" AS double),
                        1
                    )
                END AS "effective_field_goal_percentage",
                CASE
                    WHEN COALESCE("aps"."field_goals_attempted_total", 0) > 0
                    THEN ROUND(
                        CAST("aps"."three_pointers_attempted_total" AS double)
                        / CAST("aps"."field_goals_attempted_total" AS double),
                        3
                    )
                END AS "three_point_attempt_rate",
                CASE
                    WHEN COALESCE("aps"."field_goals_attempted_total", 0) > 0
                    THEN ROUND(
                        CAST("aps"."free_throws_attempted_total" AS double)
                        / CAST("aps"."field_goals_attempted_total" AS double),
                        3
                    )
                END AS "free_throw_attempt_rate",
                CASE
                    WHEN (
                        2.0 * (
                            COALESCE("aps"."field_goals_attempted_total", 0)
                            + (0.44 * COALESCE("aps"."free_throws_attempted_total", 0))
                        )
                    ) <> 0
                    THEN ROUND(
                        100.0 * CAST("aps"."points_total" AS double) / (
                            2.0 * (
                                CAST("aps"."field_goals_attempted_total" AS double)
                                + (0.44 * CAST("aps"."free_throws_attempted_total" AS double))
                            )
                        ),
                        1
                    )
                END AS "true_shooting_percentage",
                CASE
                    WHEN COALESCE("aps"."seconds_played_total", 0) > 0
                     AND (
                        COALESCE("ctx"."team_field_goals_attempted_total", 0)
                        + (0.44 * COALESCE("ctx"."team_free_throws_attempted_total", 0))
                        + COALESCE("ctx"."team_turnovers_total", 0)
                     ) <> 0
                    THEN ROUND(
                        100.0 * (
                            (
                                CAST("aps"."field_goals_attempted_total" AS double)
                                + (0.44 * CAST("aps"."free_throws_attempted_total" AS double))
                                + CAST("aps"."turnovers_total" AS double)
                            ) * (CAST("ctx"."team_seconds_played_total" AS double) / 300.0)
                        ) / (
                            (CAST("aps"."seconds_played_total" AS double) / 60.0)
                            * (
                                CAST("ctx"."team_field_goals_attempted_total" AS double)
                                + (0.44 * CAST("ctx"."team_free_throws_attempted_total" AS double))
                                + CAST("ctx"."team_turnovers_total" AS double)
                            )
                        ),
                        1
                    )
                END AS "usage_percentage",
                CASE
                    WHEN COALESCE("aps"."seconds_played_total", 0) > 0
                     AND COALESCE("aps"."possessions_total", 0) > 0
                    THEN ROUND(
                        48.0 * (CAST("aps"."possessions_total" AS double) / 2.0)
                        / (CAST("aps"."seconds_played_total" AS double) / 60.0),
                        1
                    )
                END AS "pace",
                CASE
                    WHEN COALESCE("ppc"."pie_denominator", 0) <> 0
                    THEN (
                        CAST("aps"."points_total" AS double)
                        + CAST("aps"."field_goals_made_total" AS double)
                        + CAST("aps"."free_throws_made_total" AS double)
                        - CAST("aps"."field_goals_attempted_total" AS double)
                        - CAST("aps"."free_throws_attempted_total" AS double)
                        + CAST("aps"."rebounds_defensive_total" AS double)
                        + (0.5 * CAST("aps"."rebounds_offensive_total" AS double))
                        + CAST("aps"."assists_total" AS double)
                        + CAST("aps"."steals_total" AS double)
                        + (0.5 * CAST("aps"."blocks_total" AS double))
                        - CAST("aps"."fouls_personal_total" AS double)
                        - CAST("aps"."turnovers_total" AS double)
                    ) / CAST("ppc"."pie_denominator" AS double)
                END AS "pie",
                CASE
                    WHEN COALESCE("prov"."defensive_possessions_total", 0) > 0
                    THEN ROUND(
                        100.0 * CAST("aps"."steals_total" AS double)
                        / CAST("prov"."defensive_possessions_total" AS double),
                        1
                    )
                END AS "steal_percentage",
                CASE
                    WHEN COALESCE("prov"."opponent_two_point_attempts_while_on_court_total", 0) > 0
                    THEN ROUND(
                        100.0 * CAST("aps"."blocks_total" AS double)
                        / CAST("prov"."opponent_two_point_attempts_while_on_court_total" AS double),
                        1
                    )
                END AS "block_percentage"
            FROM "agg_player_season" AS "aps"
            LEFT JOIN "player_team_context" AS "ctx"
                ON "aps"."person_id" = "ctx"."person_id"
               AND "aps"."season_year" = "ctx"."season_year"
               AND "aps"."raw_season_type_code" = "ctx"."raw_season_type_code"
            LEFT JOIN "player_pie_context" AS "ppc"
                ON "aps"."person_id" = "ppc"."person_id"
               AND "aps"."season_year" = "ppc"."season_year"
               AND "aps"."raw_season_type_code" = "ppc"."raw_season_type_code"
            LEFT JOIN "vw_player_season_provenance_debug" AS "prov"
                ON "aps"."person_id" = "prov"."player_id"
               AND "aps"."season_year" = "prov"."season_year"
               AND "aps"."season_type" = "prov"."season_type"
            """
        ).fetch_arrow_table()


def build_player_percentile_rows(
    agg_player_table: pa.Table,
    advanced_source_table: pa.Table,
) -> list[dict[str, Any]]:
    advanced_rows_by_key: dict[tuple[int, str, str], dict[str, Any]] = {}
    for row in advanced_source_table.to_pylist():
        person_id = to_int_or_none(row.get("person_id"))
        season_year = to_str_or_none(row.get("season_year"))
        season_type = to_str_or_none(row.get("season_type"))
        if person_id is None or season_year is None or season_type is None:
            continue
        advanced_rows_by_key[(person_id, season_year, season_type)] = row

    rows: list[dict[str, Any]] = []
    for row in agg_player_table.to_pylist():
        person_id = to_int_or_none(row.get("person_id"))
        season_year = to_str_or_none(row.get("season_year"))
        season_type = to_str_or_none(row.get("season_type"))
        raw_season_type_code = to_str_or_none(row.get("raw_season_type_code"))
        if person_id is None or season_year is None or season_type is None or raw_season_type_code is None:
            continue

        enriched = dict(row)
        enriched.update(advanced_rows_by_key.get((person_id, season_year, season_type), {}))
        rows.append(enriched)

    attach_percentiles(
        rows,
        metric_specs=PLAYER_PERCENTILE_SPECS,
        group_fields=("season_year", "raw_season_type_code"),
    )

    final_rows: list[dict[str, Any]] = []
    for row in rows:
        final_row: dict[str, Any] = {
            "person_id": to_int_or_none(row.get("person_id")),
            "current_player_sk": to_int_or_none(row.get("current_player_sk")),
            "season_year": to_str_or_none(row.get("season_year")),
            "season_start_year": to_int_or_none(row.get("season_start_year")),
            "raw_season_type_code": to_str_or_none(row.get("raw_season_type_code")),
            "season_type": to_str_or_none(row.get("season_type")),
        }
        for field_name in PLAYER_PERCENTILE_FIELDS:
            final_row[field_name] = to_int_or_none(row.get(field_name))
        final_rows.append(final_row)

    final_rows.sort(
        key=lambda row: (
            row.get("person_id") if row.get("person_id") is not None else -1,
            row.get("season_start_year") if row.get("season_start_year") is not None else -1,
            row.get("raw_season_type_code") or "",
        )
    )
    return final_rows


def finalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    for index, row in enumerate(rows, start=1):
        row["player_season_percentiles_sk"] = index
        row["record_source"] = RECORD_SOURCE
        row["created_at_utc"] = run_ts
        row["updated_at_utc"] = run_ts
    return rows


def main() -> None:
    s3_client = boto3.client("s3")

    agg_player_table = read_parquet_table_from_s3(s3_client, PLAYER_AGG_SOURCE_KEY, list(PLAYER_AGG_SCHEMA.names))
    dim_player_table = read_parquet_table_from_s3(s3_client, DIM_PLAYER_SOURCE_KEY, DIM_PLAYER_REQUIRED_COLUMNS)
    player_fact_table = read_parquet_table_from_s3(s3_client, PLAYER_FACT_SOURCE_KEY, list(PLAYER_FACT_SCHEMA.names))
    team_fact_table = read_parquet_table_from_s3(s3_client, TEAM_FACT_SOURCE_KEY, list(TEAM_FACT_SCHEMA.names))
    player_possession_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_POSSESSION_CONTEXT_SOURCE_KEY,
        PLAYER_POSSESSION_CONTEXT_REQUIRED_COLUMNS,
    )
    player_defensive_shot_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        PLAYER_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS,
    )

    advanced_source_table = _build_player_advanced_source_table(
        agg_player_table,
        dim_player_table,
        player_fact_table,
        team_fact_table,
        player_possession_context_table,
        player_defensive_shot_context_table,
    )
    rows = build_player_percentile_rows(agg_player_table, advanced_source_table)

    write_parquet_to_s3(finalize_rows(rows), TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
