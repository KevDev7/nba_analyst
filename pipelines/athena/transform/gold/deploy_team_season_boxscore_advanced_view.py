"""
Create a canonical Athena view for team-season boxscore advanced stats.

This serving view keeps hybrid possession and shot-context denominators in
`agg_team_season`, while using enriched silver team box score context for
bookkeeping-heavy metrics where official team rebounds and total turnovers are
more trustworthy.
"""

from __future__ import annotations

try:
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        DIM_TEAM_TABLE,
        SILVER_TEAM_TABLE,
        TEAM_AGG_TABLE,
        TEAM_FACT_TABLE,
        TEAM_SEASON_PERCENTILES_TABLE,
        discover_table_columns,
        load_settings,
    )
except ModuleNotFoundError:
    from athena_view_helpers import (  # type: ignore[no-redef]
        AthenaClient,
        DIM_TEAM_TABLE,
        SILVER_TEAM_TABLE,
        TEAM_AGG_TABLE,
        TEAM_FACT_TABLE,
        TEAM_SEASON_PERCENTILES_TABLE,
        discover_table_columns,
        load_settings,
    )


VIEW_NAME = "vw_team_season_boxscore_advanced"

TEAM_ADVANCED_PERCENTILE_COLUMNS = [
    "offensive_rating_percentile",
    "defensive_rating_percentile",
    "net_rating_percentile",
    "assist_percentage_percentile",
    "ast_to_turnover_ratio_percentile",
    "assist_ratio_percentile",
    "offensive_rebound_percentage_percentile",
    "defensive_rebound_percentage_percentile",
    "rebound_percentage_percentile",
    "steal_percentage_percentile",
    "block_percentage_percentile",
    "turnover_ratio_percentile",
    "effective_field_goal_percentage_percentile",
    "three_point_attempt_rate_percentile",
    "free_throw_attempt_rate_percentile",
    "true_shooting_percentage_percentile",
    "pace_percentile",
    "pie_percentile",
]


def _build_percentile_select_list(percentile_alias: str) -> str:
    return ",\n".join(
        f'    "{percentile_alias}"."{column_name}" AS "{column_name}"'
        for column_name in TEAM_ADVANCED_PERCENTILE_COLUMNS
    )


def build_view_sql(
    view_name: str,
    *,
    include_percentiles: bool = True,
    percentile_columns: list[tuple[str, str]] | None = None,
) -> str:
    team_minutes_total = '(CAST("ats"."seconds_played_total" AS double) / 60.0)'
    display_minutes_total = '(CAST("ats"."seconds_played_total" AS double) / 300.0)'

    hybrid_standard_poss = '(CAST(COALESCE("ats"."possessions_total", 0) AS double) / 2.0)'

    boxscore_possessions_used = (
        '(CAST(COALESCE("bctx"."field_goals_attempted_total", 0) AS double) '
        '+ (0.44 * CAST(COALESCE("bctx"."free_throws_attempted_total", 0) AS double)) '
        '+ CAST(COALESCE("bctx"."assists_total", 0) AS double) '
        '+ CAST(COALESCE("bctx"."turnovers_total", 0) AS double))'
    )
    pie_numerator = (
        '(CAST(COALESCE("ats"."points_for_total", 0) AS double) '
        '+ CAST(COALESCE("ats"."field_goals_made_total", 0) AS double) '
        '+ CAST(COALESCE("ats"."free_throws_made_total", 0) AS double) '
        '- CAST(COALESCE("ats"."field_goals_attempted_total", 0) AS double) '
        '- CAST(COALESCE("ats"."free_throws_attempted_total", 0) AS double) '
        '+ CAST(COALESCE("ats"."rebounds_defensive_total", 0) AS double) '
        '+ (0.5 * CAST(COALESCE("ats"."rebounds_offensive_total", 0) AS double)) '
        '+ CAST(COALESCE("ats"."assists_total", 0) AS double) '
        '+ CAST(COALESCE("ats"."steals_total", 0) AS double) '
        '+ (0.5 * CAST(COALESCE("ats"."blocks_total", 0) AS double)) '
        '- CAST(COALESCE("ats"."fouls_personal_total", 0) AS double) '
        '- CAST(COALESCE("ats"."turnovers_total", 0) AS double))'
    )
    percentile_select_list = ""
    percentile_join_sql = ""
    if include_percentiles:
        if percentile_columns is not None:
            percentile_column_set = {column_name for column_name, _ in percentile_columns}
            required_percentile_columns = {
                "team_id",
                "season_year",
                "raw_season_type_code",
                *TEAM_ADVANCED_PERCENTILE_COLUMNS,
            }
            missing_percentiles = sorted(required_percentile_columns - percentile_column_set)
            if missing_percentiles:
                raise RuntimeError(
                    "vw_team_season_boxscore_advanced requires team_season_percentiles columns: "
                    + ", ".join(missing_percentiles)
                )
        percentile_select_list = ",\n" + _build_percentile_select_list("tsp")
        percentile_join_sql = f"""
LEFT JOIN "{TEAM_SEASON_PERCENTILES_TABLE}" AS "tsp"
    ON "ats"."team_id" = "tsp"."team_id"
   AND "ats"."season_year" = "tsp"."season_year"
   AND "ats"."raw_season_type_code" = "tsp"."raw_season_type_code"
""".rstrip()

    return f"""-- Auto-generated team boxscore advanced serving view.
-- Re-run deploy_team_season_boxscore_advanced_view.py after changing agg_team_season,
-- fct_team_game, boxscore_team_game, dim_team, or team_season_percentiles columns used below.
CREATE OR REPLACE VIEW "{view_name}" AS
WITH "team_game_context" AS (
    SELECT
        "ftg"."team_id",
        "ftg"."season_year",
        "ftg"."raw_season_type_code",
        SUM(COALESCE("opp"."field_goals_made", 0)) AS "opponent_field_goals_made_total",
        SUM(COALESCE("opp"."field_goals_attempted", 0)) AS "opponent_field_goals_attempted_total",
        SUM(COALESCE("opp"."free_throws_attempted", 0)) AS "opponent_free_throws_attempted_total",
        SUM(COALESCE("opp"."rebounds_defensive", 0)) AS "opponent_rebounds_defensive_total",
        SUM(COALESCE("opp"."rebounds_offensive", 0)) AS "opponent_rebounds_offensive_total",
        SUM(COALESCE("opp"."rebounds_total", 0)) AS "opponent_rebounds_total",
        SUM(COALESCE("opp"."turnovers", 0)) AS "opponent_turnovers_total",
        SUM(
            CAST(COALESCE("ftg"."score", 0) AS double)
            + CAST(COALESCE("ftg"."field_goals_made", 0) AS double)
            + CAST(COALESCE("ftg"."free_throws_made", 0) AS double)
            - CAST(COALESCE("ftg"."field_goals_attempted", 0) AS double)
            - CAST(COALESCE("ftg"."free_throws_attempted", 0) AS double)
            + CAST(COALESCE("ftg"."rebounds_defensive", 0) AS double)
            + (0.5 * CAST(COALESCE("ftg"."rebounds_offensive", 0) AS double))
            + CAST(COALESCE("ftg"."assists", 0) AS double)
            + CAST(COALESCE("ftg"."steals", 0) AS double)
            + (0.5 * CAST(COALESCE("ftg"."blocks", 0) AS double))
            - CAST(COALESCE("ftg"."fouls_personal", 0) AS double)
            - CAST(COALESCE("ftg"."turnovers", 0) AS double)
            + CAST(COALESCE("opp"."score", 0) AS double)
            + CAST(COALESCE("opp"."field_goals_made", 0) AS double)
            + CAST(COALESCE("opp"."free_throws_made", 0) AS double)
            - CAST(COALESCE("opp"."field_goals_attempted", 0) AS double)
            - CAST(COALESCE("opp"."free_throws_attempted", 0) AS double)
            + CAST(COALESCE("opp"."rebounds_defensive", 0) AS double)
            + (0.5 * CAST(COALESCE("opp"."rebounds_offensive", 0) AS double))
            + CAST(COALESCE("opp"."assists", 0) AS double)
            + CAST(COALESCE("opp"."steals", 0) AS double)
            + (0.5 * CAST(COALESCE("opp"."blocks", 0) AS double))
            - CAST(COALESCE("opp"."fouls_personal", 0) AS double)
            - CAST(COALESCE("opp"."turnovers", 0) AS double)
        ) AS "pie_denominator"
    FROM "{TEAM_FACT_TABLE}" AS "ftg"
    INNER JOIN "{TEAM_FACT_TABLE}" AS "opp"
        ON "ftg"."game_id" = "opp"."game_id"
       AND "ftg"."team_id" = "opp"."opponent_team_id"
       AND "ftg"."opponent_team_id" = "opp"."team_id"
    GROUP BY 1, 2, 3
),
"boxscore_enriched" AS (
    SELECT
        LPAD(CAST("gameid" AS varchar), 10, '0') AS "game_id",
        "teamid" AS "team_id",
        "score",
        "fieldgoalsmade" AS "field_goals_made",
        "fieldgoalsattempted" AS "field_goals_attempted",
        "freethrowsmade" AS "free_throws_made",
        "freethrowsattempted" AS "free_throws_attempted",
        "threepointersmade" AS "three_pointers_made",
        "assists",
        "blocks",
        "foulspersonal" AS "fouls_personal",
        "steals",
        "turnoverstotal" AS "turnovers_total",
        "reboundsoffensive" + COALESCE("reboundsteamoffensive", 0) AS "rebounds_offensive_total",
        "reboundsdefensive" + COALESCE("reboundsteamdefensive", 0) AS "rebounds_defensive_total",
        "reboundstotal" AS "rebounds_total",
        SUBSTR(LPAD(CAST("gameid" AS varchar), 10, '0'), 1, 3) AS "raw_season_type_code",
        CASE
            WHEN CAST(SUBSTR(LPAD(CAST("gameid" AS varchar), 10, '0'), 4, 2) AS integer) <= 50
                THEN CAST(2000 + CAST(SUBSTR(LPAD(CAST("gameid" AS varchar), 10, '0'), 4, 2) AS integer) AS integer)
            ELSE CAST(1900 + CAST(SUBSTR(LPAD(CAST("gameid" AS varchar), 10, '0'), 4, 2) AS integer) AS integer)
        END AS "season_start_year"
    FROM "{SILVER_TEAM_TABLE}"
    WHERE "teamid" IS NOT NULL
),
"paired_games" AS (
    SELECT
        "t"."team_id",
        CONCAT(
            CAST("t"."season_start_year" AS varchar),
            '-',
            LPAD(CAST(MOD("t"."season_start_year" + 1, 100) AS varchar), 2, '0')
        ) AS "season_year",
        "t"."raw_season_type_code",
        "t"."field_goals_made" AS "field_goals_made",
        "t"."field_goals_attempted" AS "field_goals_attempted",
        "t"."free_throws_made" AS "free_throws_made",
        "t"."free_throws_attempted" AS "free_throws_attempted",
        "t"."three_pointers_made" AS "three_pointers_made",
        "t"."assists" AS "assists",
        "t"."blocks" AS "blocks",
        "t"."fouls_personal" AS "fouls_personal",
        "t"."steals" AS "steals",
        "t"."turnovers_total" AS "turnovers_total",
        "t"."rebounds_offensive_total" AS "rebounds_offensive_total",
        "t"."rebounds_defensive_total" AS "rebounds_defensive_total",
        "t"."rebounds_total" AS "rebounds_total",
        "o"."rebounds_offensive_total" AS "opponent_rebounds_offensive_total",
        "o"."rebounds_defensive_total" AS "opponent_rebounds_defensive_total",
        "o"."rebounds_total" AS "opponent_rebounds_total"
    FROM "boxscore_enriched" AS "t"
    INNER JOIN "boxscore_enriched" AS "o"
        ON "t"."game_id" = "o"."game_id"
       AND "t"."team_id" <> "o"."team_id"
),
"season_boxscore_context" AS (
    SELECT
        "team_id",
        "season_year",
        "raw_season_type_code",
        SUM(COALESCE("field_goals_made", 0)) AS "field_goals_made_total",
        SUM(COALESCE("field_goals_attempted", 0)) AS "field_goals_attempted_total",
        SUM(COALESCE("free_throws_made", 0)) AS "free_throws_made_total",
        SUM(COALESCE("free_throws_attempted", 0)) AS "free_throws_attempted_total",
        SUM(COALESCE("three_pointers_made", 0)) AS "three_pointers_made_total",
        SUM(COALESCE("assists", 0)) AS "assists_total",
        SUM(COALESCE("blocks", 0)) AS "blocks_total",
        SUM(COALESCE("fouls_personal", 0)) AS "fouls_personal_total",
        SUM(COALESCE("steals", 0)) AS "steals_total",
        SUM(COALESCE("turnovers_total", 0)) AS "turnovers_total",
        SUM(COALESCE("rebounds_offensive_total", 0)) AS "rebounds_offensive_total",
        SUM(COALESCE("rebounds_defensive_total", 0)) AS "rebounds_defensive_total",
        SUM(COALESCE("rebounds_total", 0)) AS "rebounds_total",
        SUM(COALESCE("opponent_rebounds_offensive_total", 0)) AS "opponent_rebounds_offensive_total",
        SUM(COALESCE("opponent_rebounds_defensive_total", 0)) AS "opponent_rebounds_defensive_total",
        SUM(COALESCE("opponent_rebounds_total", 0)) AS "opponent_rebounds_total"
    FROM "paired_games"
    GROUP BY 1, 2, 3
)
SELECT
    "ats"."team_id" AS "team_id",
    "ats"."season_year" AS "season_year",
    "ats"."season_type" AS "season_type",
    COALESCE("dt"."team_abbreviation", "dt"."team_name") AS "team",
    "ats"."games_played" AS "games_played",
    "ats"."wins" AS "wins",
    "ats"."losses" AS "losses",
    CAST(ROUND({display_minutes_total}, 0) AS bigint) AS "minutes",
    CASE WHEN COALESCE("ats"."possessions_total", 0) > 0
      THEN ROUND(CAST("ats"."points_for_total" AS double) * 100.0 / {hybrid_standard_poss}, 1)
    END AS "offensive_rating",
    CASE WHEN COALESCE("ats"."possessions_total", 0) > 0
      THEN ROUND(CAST("ats"."points_against_total" AS double) * 100.0 / {hybrid_standard_poss}, 1)
    END AS "defensive_rating",
    CASE WHEN COALESCE("ats"."possessions_total", 0) > 0
      THEN ROUND(
        (CAST("ats"."points_for_total" AS double) * 100.0 / {hybrid_standard_poss})
        - (CAST("ats"."points_against_total" AS double) * 100.0 / {hybrid_standard_poss}),
        1
      )
    END AS "net_rating",
    CASE WHEN COALESCE("ats"."field_goals_made_total", 0) > 0
      THEN ROUND(
        CAST("ats"."assists_total" AS double) * 100.0
        / CAST("ats"."field_goals_made_total" AS double),
        1
      )
    END AS "assist_percentage",
    CASE WHEN COALESCE("bctx"."turnovers_total", 0) > 0
      THEN ROUND(CAST("bctx"."assists_total" AS double) / CAST("bctx"."turnovers_total" AS double), 2)
    END AS "ast_to_turnover_ratio",
    CASE WHEN {boxscore_possessions_used} > 0
      THEN ROUND(CAST("bctx"."assists_total" AS double) * 100.0 / {boxscore_possessions_used}, 1)
    END AS "assist_ratio",
    CASE WHEN (COALESCE("bctx"."rebounds_offensive_total", 0)
          + COALESCE("bctx"."opponent_rebounds_defensive_total", 0)) > 0
      THEN ROUND(
        CAST("bctx"."rebounds_offensive_total" AS double) * 100.0
        / (CAST("bctx"."rebounds_offensive_total" AS double)
           + CAST("bctx"."opponent_rebounds_defensive_total" AS double)),
        1
      )
    END AS "offensive_rebound_percentage",
    CASE WHEN (COALESCE("bctx"."rebounds_defensive_total", 0)
          + COALESCE("bctx"."opponent_rebounds_offensive_total", 0)) > 0
      THEN ROUND(
        CAST("bctx"."rebounds_defensive_total" AS double) * 100.0
        / (CAST("bctx"."rebounds_defensive_total" AS double)
           + CAST("bctx"."opponent_rebounds_offensive_total" AS double)),
        1
      )
    END AS "defensive_rebound_percentage",
    CASE WHEN (COALESCE("bctx"."rebounds_total", 0)
          + COALESCE("bctx"."opponent_rebounds_total", 0)) > 0
      THEN ROUND(
        CAST("bctx"."rebounds_total" AS double) * 100.0
        / (CAST("bctx"."rebounds_total" AS double)
           + CAST("bctx"."opponent_rebounds_total" AS double)),
        1
      )
    END AS "rebound_percentage",
    CASE WHEN COALESCE("ats"."defensive_possessions_total", 0) > 0
      THEN ROUND(
        CAST("ats"."steals_total" AS double) * 100.0
        / CAST("ats"."defensive_possessions_total" AS double),
        1
      )
    END AS "steal_percentage",
    CASE WHEN COALESCE("ats"."opponent_two_point_attempts_total", 0) > 0
      THEN ROUND(
        CAST("ats"."blocks_total" AS double) * 100.0
        / CAST("ats"."opponent_two_point_attempts_total" AS double),
        1
      )
    END AS "block_percentage",
    CASE WHEN COALESCE("ats"."possessions_total", 0) > 0
      THEN ROUND(CAST("ats"."turnovers_total" AS double) * 100.0 / {hybrid_standard_poss}, 1)
    END AS "turnover_ratio",
    CASE WHEN COALESCE("ats"."field_goals_attempted_total", 0) > 0
      THEN ROUND(
        ((CAST("ats"."field_goals_made_total" AS double)
          + (0.5 * CAST("ats"."three_pointers_made_total" AS double)))
         / CAST("ats"."field_goals_attempted_total" AS double)) * 100.0,
        1
      )
    END AS "effective_field_goal_percentage",
    CASE WHEN COALESCE("ats"."field_goals_attempted_total", 0) > 0
      THEN ROUND(
        CAST("ats"."three_pointers_attempted_total" AS double)
        / CAST("ats"."field_goals_attempted_total" AS double),
        3
      )
    END AS "three_point_attempt_rate",
    CASE WHEN COALESCE("ats"."field_goals_attempted_total", 0) > 0
      THEN ROUND(
        CAST("ats"."free_throws_attempted_total" AS double)
        / CAST("ats"."field_goals_attempted_total" AS double),
        3
      )
    END AS "free_throw_attempt_rate",
    CASE WHEN (COALESCE("ats"."field_goals_attempted_total", 0)
          + (0.44 * COALESCE("ats"."free_throws_attempted_total", 0))) > 0
      THEN ROUND(
        CAST("ats"."points_for_total" AS double) * 100.0
        / (2.0 * (CAST("ats"."field_goals_attempted_total" AS double)
                + (0.44 * CAST("ats"."free_throws_attempted_total" AS double)))),
        1
      )
    END AS "true_shooting_percentage",
    CASE WHEN {team_minutes_total} > 0 AND COALESCE("ats"."possessions_total", 0) > 0
      THEN ROUND({hybrid_standard_poss} * 240.0 / {team_minutes_total}, 2)
    END AS "pace",
    CASE WHEN COALESCE("ctx"."pie_denominator", 0) <> 0
      THEN ROUND(({pie_numerator} / CAST("ctx"."pie_denominator" AS double)) * 100.0, 1)
    END AS "pie",
    CASE WHEN COALESCE("ats"."possessions_total", 0) > 0
      THEN CAST(ROUND({hybrid_standard_poss}, 0) AS bigint)
    END AS "possessions"
{percentile_select_list}
FROM "{TEAM_AGG_TABLE}" AS "ats"
LEFT JOIN "{DIM_TEAM_TABLE}" AS "dt"
    ON "ats"."team_id" = "dt"."team_id"
   AND COALESCE("dt"."is_current", 0) = 1
LEFT JOIN "team_game_context" AS "ctx"
    ON "ats"."team_id" = "ctx"."team_id"
   AND "ats"."season_year" = "ctx"."season_year"
   AND "ats"."raw_season_type_code" = "ctx"."raw_season_type_code"
LEFT JOIN "season_boxscore_context" AS "bctx"
    ON "ats"."team_id" = "bctx"."team_id"
   AND "ats"."season_year" = "bctx"."season_year"
   AND "ats"."raw_season_type_code" = "bctx"."raw_season_type_code"
{percentile_join_sql}
"""


def deploy_team_season_boxscore_advanced_view() -> None:
    settings = load_settings()
    athena_client = AthenaClient(settings)
    percentile_columns = discover_table_columns(athena_client, settings.database, TEAM_SEASON_PERCENTILES_TABLE)
    if not percentile_columns:
        raise RuntimeError(f"No columns found for {settings.database}.{TEAM_SEASON_PERCENTILES_TABLE}")

    sql = build_view_sql(VIEW_NAME, percentile_columns=percentile_columns)
    athena_client.execute(sql)
    print(f"Created or replaced view: {settings.database}.{VIEW_NAME}")


def main() -> None:
    deploy_team_season_boxscore_advanced_view()


if __name__ == "__main__":
    main()
