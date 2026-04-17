"""
Create Athena internal debug view for player-season provenance.

Managed views:
  - vw_player_season_provenance_debug
"""

from __future__ import annotations

try:
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        DIM_PLAYER_TABLE,
        PLAYER_AGG_TABLE,
        PLAYER_PROVENANCE_DEBUG_VIEW,
        SILVER_PLAYER_DEFENSIVE_SHOT_CONTEXT_TABLE,
        SILVER_PLAYER_POSSESSION_CONTEXT_TABLE,
        discover_table_columns,
        load_settings,
        select_internal_player_agg_columns,
    )
except ModuleNotFoundError:
    from athena_view_helpers import (  # type: ignore[no-redef]
        AthenaClient,
        DIM_PLAYER_TABLE,
        PLAYER_AGG_TABLE,
        PLAYER_PROVENANCE_DEBUG_VIEW,
        SILVER_PLAYER_DEFENSIVE_SHOT_CONTEXT_TABLE,
        SILVER_PLAYER_POSSESSION_CONTEXT_TABLE,
        discover_table_columns,
        load_settings,
        select_internal_player_agg_columns,
    )


VIEW_NAME = PLAYER_PROVENANCE_DEBUG_VIEW


def build_view_sql(view_name: str, base_columns: list[tuple[str, str]]) -> str:
    column_set = {column_name for column_name, _ in base_columns}
    required_columns = {
        "person_id",
        "current_player_sk",
        "season_year",
        "raw_season_type_code",
        "season_type",
        "primary_team_abbreviation",
        "primary_team_name",
        "games_played",
        "possessions_total",
    }
    missing = sorted(required_columns - column_set)
    if missing:
        raise RuntimeError(
            "vw_player_season_provenance_debug requires agg_player_season columns: " + ", ".join(missing)
        )

    return f"""-- Auto-generated internal Athena debug view for player-season provenance.
CREATE OR REPLACE VIEW "{view_name}" AS
WITH "possession_context" AS (
    SELECT
        "person_id" AS "player_id",
        "season_year",
        "season_type_code" AS "raw_season_type_code",
        SUM(COALESCE("exact_game_flag", 0)) AS "exact_possession_games",
        SUM(COALESCE("ot_fallback_game_flag", 0)) AS "ot_fallback_possession_games",
        SUM(COALESCE("event_estimated_game_flag", 0)) AS "event_estimated_possession_games",
        SUM(COALESCE("boxscore_estimated_game_flag", 0)) AS "boxscore_estimated_possession_games",
        SUM(COALESCE("missing_game_flag", 0)) AS "missing_possession_games",
        SUM(COALESCE("offensive_possessions", 0)) AS "offensive_possessions_total",
        SUM(COALESCE("defensive_possessions", 0)) AS "defensive_possessions_total",
        SUM(COALESCE("team_points_for_while_on_court", 0)) AS "team_points_for_while_on_court_total",
        SUM(COALESCE("team_points_against_while_on_court", 0)) AS "team_points_against_while_on_court_total"
    FROM "{SILVER_PLAYER_POSSESSION_CONTEXT_TABLE}"
    GROUP BY 1, 2, 3
),
"shot_context" AS (
    SELECT
        "person_id" AS "player_id",
        "season_year",
        "season_type_code" AS "raw_season_type_code",
        SUM(COALESCE("exact_game_flag", 0)) AS "exact_shot_context_games",
        SUM(COALESCE("event_estimated_game_flag", 0)) AS "event_estimated_shot_context_games",
        SUM(COALESCE("boxscore_estimated_game_flag", 0)) AS "boxscore_estimated_shot_context_games",
        SUM(COALESCE("missing_game_flag", 0)) AS "missing_shot_context_games",
        SUM(COALESCE("opponent_two_point_attempts_while_on_court", 0)) AS "opponent_two_point_attempts_while_on_court_total"
    FROM "{SILVER_PLAYER_DEFENSIVE_SHOT_CONTEXT_TABLE}"
    GROUP BY 1, 2, 3
),
"current_player_dim" AS (
    SELECT
        "player_sk",
        "display_name",
        "player_name"
    FROM "{DIM_PLAYER_TABLE}"
    WHERE "is_current" = 1
)
SELECT
    "aps"."person_id" AS "player_id",
    COALESCE("cpd"."display_name", "cpd"."player_name") AS "player_name",
    "aps"."season_year" AS "season_year",
    "aps"."season_type" AS "season_type",
    COALESCE("aps"."primary_team_abbreviation", "aps"."primary_team_name") AS "team",
    COALESCE("pc"."exact_possession_games", 0) AS "exact_possession_games",
    COALESCE("pc"."ot_fallback_possession_games", 0) AS "ot_fallback_possession_games",
    COALESCE("pc"."event_estimated_possession_games", 0) AS "event_estimated_possession_games",
    COALESCE("pc"."boxscore_estimated_possession_games", 0) AS "boxscore_estimated_possession_games",
    COALESCE("pc"."missing_possession_games", 0) AS "missing_possession_games",
    CASE
        WHEN COALESCE("aps"."games_played", 0) > 0
        THEN ROUND(
            100.0 * (
                CAST(COALESCE("pc"."exact_possession_games", 0) AS double)
                + CAST(COALESCE("pc"."ot_fallback_possession_games", 0) AS double)
                + CAST(COALESCE("pc"."event_estimated_possession_games", 0) AS double)
                + CAST(COALESCE("pc"."boxscore_estimated_possession_games", 0) AS double)
            ) / CAST("aps"."games_played" AS double),
            1
        )
    END AS "possession_coverage_pct",
    CASE
        WHEN COALESCE("pc"."exact_possession_games", 0) > 0
         AND COALESCE("pc"."ot_fallback_possession_games", 0) = 0
         AND COALESCE("pc"."event_estimated_possession_games", 0) = 0
         AND COALESCE("pc"."boxscore_estimated_possession_games", 0) = 0
        THEN 'exact'
        WHEN COALESCE("pc"."exact_possession_games", 0) = 0
         AND COALESCE("pc"."ot_fallback_possession_games", 0) > 0
         AND COALESCE("pc"."event_estimated_possession_games", 0) = 0
         AND COALESCE("pc"."boxscore_estimated_possession_games", 0) = 0
        THEN 'ot_fallback'
        WHEN COALESCE("pc"."exact_possession_games", 0) = 0
         AND COALESCE("pc"."ot_fallback_possession_games", 0) = 0
         AND COALESCE("pc"."event_estimated_possession_games", 0) > 0
         AND COALESCE("pc"."boxscore_estimated_possession_games", 0) = 0
        THEN 'event_estimated'
        WHEN COALESCE("pc"."exact_possession_games", 0) = 0
         AND COALESCE("pc"."ot_fallback_possession_games", 0) = 0
         AND COALESCE("pc"."event_estimated_possession_games", 0) = 0
         AND COALESCE("pc"."boxscore_estimated_possession_games", 0) > 0
        THEN 'boxscore_estimated'
        WHEN (
            COALESCE("pc"."exact_possession_games", 0)
            + COALESCE("pc"."ot_fallback_possession_games", 0)
            + COALESCE("pc"."event_estimated_possession_games", 0)
            + COALESCE("pc"."boxscore_estimated_possession_games", 0)
        ) > 0
        THEN 'mixed'
    END AS "possession_source_method",
    COALESCE("sc"."exact_shot_context_games", 0) AS "exact_shot_context_games",
    COALESCE("sc"."event_estimated_shot_context_games", 0) AS "event_estimated_shot_context_games",
    COALESCE("sc"."boxscore_estimated_shot_context_games", 0) AS "boxscore_estimated_shot_context_games",
    COALESCE("sc"."missing_shot_context_games", 0) AS "missing_shot_context_games",
    CASE
        WHEN COALESCE("aps"."games_played", 0) > 0
        THEN ROUND(
            100.0 * (
                CAST(COALESCE("sc"."exact_shot_context_games", 0) AS double)
                + CAST(COALESCE("sc"."event_estimated_shot_context_games", 0) AS double)
                + CAST(COALESCE("sc"."boxscore_estimated_shot_context_games", 0) AS double)
            ) / CAST("aps"."games_played" AS double),
            1
        )
    END AS "shot_context_coverage_pct",
    CASE
        WHEN COALESCE("sc"."exact_shot_context_games", 0) > 0
         AND COALESCE("sc"."event_estimated_shot_context_games", 0) = 0
         AND COALESCE("sc"."boxscore_estimated_shot_context_games", 0) = 0
        THEN 'exact'
        WHEN COALESCE("sc"."exact_shot_context_games", 0) = 0
         AND COALESCE("sc"."event_estimated_shot_context_games", 0) > 0
         AND COALESCE("sc"."boxscore_estimated_shot_context_games", 0) = 0
        THEN 'event_estimated'
        WHEN COALESCE("sc"."exact_shot_context_games", 0) = 0
         AND COALESCE("sc"."event_estimated_shot_context_games", 0) = 0
         AND COALESCE("sc"."boxscore_estimated_shot_context_games", 0) > 0
        THEN 'boxscore_estimated'
        WHEN (
            COALESCE("sc"."exact_shot_context_games", 0)
            + COALESCE("sc"."event_estimated_shot_context_games", 0)
            + COALESCE("sc"."boxscore_estimated_shot_context_games", 0)
        ) > 0
        THEN 'mixed'
    END AS "shot_context_source_method",
    COALESCE("pc"."offensive_possessions_total", 0.0) AS "offensive_possessions_total",
    COALESCE("pc"."defensive_possessions_total", 0.0) AS "defensive_possessions_total",
    CAST("aps"."possessions_total" AS double) AS "possessions_total",
    COALESCE("pc"."team_points_for_while_on_court_total", 0.0) AS "team_points_for_while_on_court_total",
    COALESCE("pc"."team_points_against_while_on_court_total", 0.0) AS "team_points_against_while_on_court_total",
    COALESCE("sc"."opponent_two_point_attempts_while_on_court_total", 0.0) AS "opponent_two_point_attempts_while_on_court_total"
FROM "{PLAYER_AGG_TABLE}" AS "aps"
LEFT JOIN "possession_context" AS "pc"
    ON "aps"."person_id" = "pc"."player_id"
   AND "aps"."season_year" = "pc"."season_year"
   AND "aps"."raw_season_type_code" = "pc"."raw_season_type_code"
LEFT JOIN "shot_context" AS "sc"
    ON "aps"."person_id" = "sc"."player_id"
   AND "aps"."season_year" = "sc"."season_year"
   AND "aps"."raw_season_type_code" = "sc"."raw_season_type_code"
LEFT JOIN "current_player_dim" AS "cpd"
    ON "aps"."current_player_sk" = "cpd"."player_sk"
"""


def deploy_player_season_provenance_debug_view() -> None:
    settings = load_settings()
    athena_client = AthenaClient(settings)
    base_columns = discover_table_columns(athena_client, settings.database, PLAYER_AGG_TABLE)
    if not base_columns:
        raise RuntimeError(f"No columns found for {settings.database}.{PLAYER_AGG_TABLE}")
    base_columns = select_internal_player_agg_columns(base_columns)

    sql = build_view_sql(VIEW_NAME, base_columns)
    athena_client.execute(f'DROP VIEW IF EXISTS "{VIEW_NAME}"')
    athena_client.execute(sql)
    print(f"Created or replaced internal view: {settings.database}.{VIEW_NAME}")


def main() -> None:
    deploy_player_season_provenance_debug_view()


if __name__ == "__main__":
    main()
