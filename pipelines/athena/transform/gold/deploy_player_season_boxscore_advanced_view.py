"""
Create Athena view for player-season boxscore-derived advanced metrics.

The view keeps `agg_player_season` as the canonical player-season numerator
surface and derives team/opponent denominator context from the exact games
the player actually appeared in.

Managed views:
  - vw_player_season_boxscore_advanced
"""

from __future__ import annotations

try:
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        DIM_PLAYER_TABLE,
        PLAYER_AGG_TABLE,
        PLAYER_FACT_TABLE,
        PLAYER_SEASON_PERCENTILES_TABLE,
        PLAYER_PROVENANCE_DEBUG_VIEW,
        TEAM_FACT_TABLE,
        discover_table_columns,
        load_settings,
        select_internal_player_agg_columns,
    )
except ModuleNotFoundError:
    from athena_view_helpers import (  # type: ignore[no-redef]
        AthenaClient,
        DIM_PLAYER_TABLE,
        PLAYER_AGG_TABLE,
        PLAYER_FACT_TABLE,
        PLAYER_SEASON_PERCENTILES_TABLE,
        PLAYER_PROVENANCE_DEBUG_VIEW,
        TEAM_FACT_TABLE,
        discover_table_columns,
        load_settings,
        select_internal_player_agg_columns,
    )


VIEW_NAME = "vw_player_season_boxscore_advanced"

PLAYER_ADVANCED_PERCENTILE_COLUMNS = [
    "minutes_percentile",
    "offensive_rating_percentile",
    "defensive_rating_percentile",
    "net_rating_percentile",
    "assist_percentage_percentile",
    "ast_to_turnover_ratio_percentile",
    "assist_ratio_percentile",
    "offensive_rebound_percentage_percentile",
    "defensive_rebound_percentage_percentile",
    "rebound_percentage_percentile",
    "turnover_ratio_percentile",
    "effective_field_goal_percentage_percentile",
    "three_point_attempt_rate_percentile",
    "free_throw_attempt_rate_percentile",
    "true_shooting_percentage_percentile",
    "usage_percentage_percentile",
    "pace_percentile",
    "pie_percentile",
    "steal_percentage_percentile",
    "block_percentage_percentile",
]

def _build_percentile_select_list(percentile_alias: str) -> str:
    return ",\n".join(
        f'    "{percentile_alias}"."{column_name}" AS "{column_name}"'
        for column_name in PLAYER_ADVANCED_PERCENTILE_COLUMNS
    )


def build_view_sql(
    view_name: str,
    base_columns: list[tuple[str, str]],
    percentile_columns: list[tuple[str, str]] | None = None,
) -> str:
    column_set = {column_name for column_name, _ in base_columns}
    required_columns = {
        "person_id",
        "current_player_sk",
        "season_year",
        "season_type",
        "raw_season_type_code",
        "age_on_jan_31",
        "primary_team_abbreviation",
        "games_played",
        "wins",
        "losses",
        "seconds_played_total",
        "points_total",
        "assists_total",
        "rebounds_total",
        "rebounds_offensive_total",
        "rebounds_defensive_total",
        "steals_total",
        "blocks_total",
        "turnovers_total",
        "field_goals_made_total",
        "field_goals_attempted_total",
        "three_pointers_made_total",
        "free_throws_made_total",
        "free_throws_attempted_total",
        "fouls_personal_total",
        "possessions_total",
    }
    missing = sorted(required_columns - column_set)
    if missing:
        raise RuntimeError(
            "vw_player_season_boxscore_advanced requires agg_player_season columns: " + ", ".join(missing)
        )

    if percentile_columns is not None:
        percentile_column_set = {column_name for column_name, _ in percentile_columns}
        required_percentile_columns = {
            "person_id",
            "season_year",
            "raw_season_type_code",
            *PLAYER_ADVANCED_PERCENTILE_COLUMNS,
        }
        missing_percentiles = sorted(required_percentile_columns - percentile_column_set)
        if missing_percentiles:
            raise RuntimeError(
                "vw_player_season_boxscore_advanced requires player_season_percentiles columns: "
                + ", ".join(missing_percentiles)
            )

    select_list = """
    "aps"."person_id" AS "player_id",
    "aps"."season_year" AS "season_year",
    "aps"."season_type" AS "season_type",
    COALESCE("cpd"."display_name", "cpd"."player_name") AS "player_name",
    "aps"."primary_team_abbreviation" AS "team",
    "aps"."age_on_jan_31" AS "age",
    "aps"."games_played" AS "games_played",
    "aps"."wins" AS "wins",
    "aps"."losses" AS "losses",
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
        WHEN COALESCE("aps"."possessions_total", 0) > 0
        THEN ROUND(CAST("aps"."possessions_total" AS double) / 2.0, 1)
    END AS "possessions",
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
""".strip()
    select_list = f'{select_list},\n{_build_percentile_select_list("psp")}'

    return f"""-- Auto-generated from the live {PLAYER_AGG_TABLE} schema plus {PLAYER_FACT_TABLE}, {TEAM_FACT_TABLE}, {DIM_PLAYER_TABLE}, {PLAYER_PROVENANCE_DEBUG_VIEW}, and {PLAYER_SEASON_PERCENTILES_TABLE}.
-- Re-run deploy_player_season_boxscore_advanced_view.py after changing agg_player_season,
-- fct_player_game, fct_team_game, dim_player, vw_player_season_provenance_debug, or player_season_percentiles columns used in the context CTEs below.
CREATE OR REPLACE VIEW "{view_name}" AS
WITH "played_player_games" AS (
    SELECT
        "game_id",
        "person_id",
        "team_id",
        "season_year",
        "raw_season_type_code"
    FROM "{PLAYER_FACT_TABLE}"
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
    INNER JOIN "{TEAM_FACT_TABLE}" AS "tg"
        ON "ppg"."game_id" = "tg"."game_id"
       AND "ppg"."team_id" = "tg"."team_id"
    INNER JOIN "{TEAM_FACT_TABLE}" AS "opp"
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
    FROM "{PLAYER_FACT_TABLE}"
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
),
"current_player_dim" AS (
    SELECT
        "player_sk",
        "person_id",
        "display_name",
        "player_name"
    FROM "{DIM_PLAYER_TABLE}"
    WHERE "is_current" = 1
)
SELECT
{select_list}
FROM "{PLAYER_AGG_TABLE}" AS "aps"
LEFT JOIN "player_team_context" AS "ctx"
    ON "aps"."person_id" = "ctx"."person_id"
   AND "aps"."season_year" = "ctx"."season_year"
   AND "aps"."raw_season_type_code" = "ctx"."raw_season_type_code"
LEFT JOIN "player_pie_context" AS "ppc"
    ON "aps"."person_id" = "ppc"."person_id"
   AND "aps"."season_year" = "ppc"."season_year"
   AND "aps"."raw_season_type_code" = "ppc"."raw_season_type_code"
LEFT JOIN "{PLAYER_PROVENANCE_DEBUG_VIEW}" AS "prov"
    ON "aps"."person_id" = "prov"."player_id"
   AND "aps"."season_year" = "prov"."season_year"
   AND "aps"."season_type" = "prov"."season_type"
LEFT JOIN "current_player_dim" AS "cpd"
    ON "aps"."current_player_sk" = "cpd"."player_sk"
LEFT JOIN "{PLAYER_SEASON_PERCENTILES_TABLE}" AS "psp"
    ON "aps"."person_id" = "psp"."person_id"
   AND "aps"."season_year" = "psp"."season_year"
   AND "aps"."raw_season_type_code" = "psp"."raw_season_type_code"
"""


def deploy_player_season_boxscore_advanced_view() -> None:
    settings = load_settings()
    athena_client = AthenaClient(settings)
    base_columns = discover_table_columns(athena_client, settings.database, PLAYER_AGG_TABLE)
    if not base_columns:
        raise RuntimeError(f"No columns found for {settings.database}.{PLAYER_AGG_TABLE}")
    base_columns = select_internal_player_agg_columns(base_columns)
    percentile_columns = discover_table_columns(athena_client, settings.database, PLAYER_SEASON_PERCENTILES_TABLE)
    if not percentile_columns:
        raise RuntimeError(f"No columns found for {settings.database}.{PLAYER_SEASON_PERCENTILES_TABLE}")

    sql = build_view_sql(VIEW_NAME, base_columns, percentile_columns)
    athena_client.execute(f'DROP VIEW IF EXISTS "{VIEW_NAME}"')
    athena_client.execute(sql)
    print(f"Created or replaced view: {settings.database}.{VIEW_NAME}")


def main() -> None:
    deploy_player_season_boxscore_advanced_view()


if __name__ == "__main__":
    main()
