from __future__ import annotations

from pipelines.athena.transform.gold.deploy_player_season_boxscore_advanced_view import (
    PLAYER_ADVANCED_PERCENTILE_COLUMNS,
)


EXPECTED_COLUMNS = [
    "player_id",
    "season_year",
    "season_type",
    "player_name",
    "team",
    "age",
    "games_played",
    "wins",
    "losses",
    "minutes",
    "offensive_rating",
    "defensive_rating",
    "net_rating",
    "assist_percentage",
    "ast_to_turnover_ratio",
    "assist_ratio",
    "offensive_rebound_percentage",
    "defensive_rebound_percentage",
    "rebound_percentage",
    "turnover_ratio",
    "effective_field_goal_percentage",
    "three_point_attempt_rate",
    "free_throw_attempt_rate",
    "true_shooting_percentage",
    "usage_percentage",
    "pace",
    "pie",
    "possessions",
    "steal_percentage",
    "block_percentage",
] + PLAYER_ADVANCED_PERCENTILE_COLUMNS


def test_boxscore_advanced_view_exposes_expected_columns(athena_client, athena_settings):
    headers, _ = athena_client.execute(
        """
        SELECT *
        FROM "vw_player_season_boxscore_advanced"
        LIMIT 1
        """
    )
    assert headers == EXPECTED_COLUMNS


def test_boxscore_advanced_view_is_queryable_and_non_empty(athena_client):
    _, rows = athena_client.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM "vw_player_season_boxscore_advanced"
        """
    )
    assert rows[0]["row_count"] > 0


def test_boxscore_advanced_view_preserves_player_season_grain(athena_client):
    _, rows = athena_client.execute(
        """
        SELECT
          COUNT(*) AS total_rows,
          COUNT(DISTINCT CAST(player_id AS VARCHAR) || '|' || season_year || '|' || season_type) AS distinct_rows
        FROM "vw_player_season_boxscore_advanced"
        """
    )
    assert rows[0]["total_rows"] == rows[0]["distinct_rows"]


def test_boxscore_advanced_metrics_are_non_null_when_denominators_are_valid(athena_client):
    _, rows = athena_client.execute(
        """
        SELECT COUNT(*) AS bad_rows
        FROM "vw_player_season_boxscore_advanced" AS view
        INNER JOIN "agg_player_season" AS aps
            ON view.player_id = aps.person_id
           AND view.season_year = aps.season_year
           AND view.season_type = aps.season_type
        INNER JOIN "vw_player_season_provenance_debug" AS prov
            ON view.player_id = prov.player_id
           AND view.season_year = prov.season_year
           AND view.season_type = prov.season_type
        WHERE (
            aps.turnovers_total > 0
            AND view.ast_to_turnover_ratio IS NULL
        ) OR (
            (
                aps.field_goals_attempted_total
                + (0.44 * aps.free_throws_attempted_total)
                + aps.assists_total
                + aps.turnovers_total
            ) > 0
            AND (
                view.assist_ratio IS NULL
                OR view.turnover_ratio IS NULL
            )
        ) OR (
            aps.field_goals_attempted_total > 0
            AND view.effective_field_goal_percentage IS NULL
        ) OR (
            (aps.field_goals_attempted_total + (0.44 * aps.free_throws_attempted_total)) > 0
            AND view.true_shooting_percentage IS NULL
        ) OR (
            aps.games_played > 0
            AND view.pie IS NULL
        ) OR (
            aps.possessions_total > 0
            AND (
                view.possessions IS NULL
                OR view.pace IS NULL
            )
        ) OR (
            prov.offensive_possessions_total > 0
            AND view.offensive_rating IS NULL
        ) OR (
            prov.defensive_possessions_total > 0
            AND view.defensive_rating IS NULL
        )
        """
    )
    assert rows[0]["bad_rows"] == 0


def test_boxscore_advanced_attempt_rates_are_null_when_fga_is_zero(athena_client):
    _, rows = athena_client.execute(
        """
        SELECT COUNT(*) AS bad_rows
        FROM "vw_player_season_boxscore_advanced" AS view
        INNER JOIN "agg_player_season" AS aps
            ON view.player_id = aps.person_id
           AND view.season_year = aps.season_year
           AND view.season_type = aps.season_type
        WHERE COALESCE(aps.field_goals_attempted_total, 0) = 0
          AND (
            view.three_point_attempt_rate IS NOT NULL
            OR view.free_throw_attempt_rate IS NOT NULL
          )
        """
    )
    assert rows[0]["bad_rows"] == 0


def test_boxscore_advanced_view_matches_hand_computed_metric_formulas(athena_client):
    _, rows = athena_client.execute(
        """
        WITH played_player_games AS (
            SELECT
                game_id,
                person_id,
                team_id,
                season_year,
                raw_season_type_code
            FROM "fct_player_game"
            WHERE person_id IS NOT NULL
              AND team_id IS NOT NULL
              AND (
                  COALESCE(did_play, 0) = 1
                  OR COALESCE(seconds_played_total, 0) > 0
              )
        ),
        player_team_context AS (
            SELECT
                ppg.person_id,
                ppg.season_year,
                ppg.raw_season_type_code,
                SUM(COALESCE(tg.seconds_played_total, 0)) AS team_seconds_played_total,
                SUM(COALESCE(tg.field_goals_made, 0)) AS team_field_goals_made_total,
                SUM(COALESCE(tg.field_goals_attempted, 0)) AS team_field_goals_attempted_total,
                SUM(COALESCE(tg.free_throws_attempted, 0)) AS team_free_throws_attempted_total,
                SUM(COALESCE(tg.turnovers, 0)) AS team_turnovers_total
            FROM played_player_games AS ppg
            INNER JOIN "fct_team_game" AS tg
                ON ppg.game_id = tg.game_id
               AND ppg.team_id = tg.team_id
            GROUP BY 1, 2, 3
        ),
        candidate AS (
            SELECT
                view.player_id,
                view.season_year,
                view.season_type,
                view.assist_ratio,
                view.effective_field_goal_percentage,
                view.true_shooting_percentage,
                view.usage_percentage,
                view.steal_percentage,
                view.block_percentage,
                view.possessions,
                view.pace,
                view.offensive_rating,
                view.defensive_rating,
                view.net_rating,
                100.0 * CAST(aps.assists_total AS double) / (
                    CAST(aps.field_goals_attempted_total AS double)
                    + (0.44 * CAST(aps.free_throws_attempted_total AS double))
                    + CAST(aps.assists_total AS double)
                    + CAST(aps.turnovers_total AS double)
                ) AS expected_assist_ratio,
                100.0 * (
                    CAST(aps.field_goals_made_total AS double)
                    + (0.5 * CAST(aps.three_pointers_made_total AS double))
                ) / CAST(aps.field_goals_attempted_total AS double) AS expected_effective_field_goal_percentage,
                100.0 * CAST(aps.points_total AS double) / (
                    2.0 * (
                        CAST(aps.field_goals_attempted_total AS double)
                        + (0.44 * CAST(aps.free_throws_attempted_total AS double))
                    )
                ) AS expected_true_shooting_percentage,
                100.0 * (
                    (
                        CAST(aps.field_goals_attempted_total AS double)
                        + (0.44 * CAST(aps.free_throws_attempted_total AS double))
                        + CAST(aps.turnovers_total AS double)
                    ) * (CAST(ctx.team_seconds_played_total AS double) / 300.0)
                ) / (
                    (CAST(aps.seconds_played_total AS double) / 60.0)
                    * (
                        CAST(ctx.team_field_goals_attempted_total AS double)
                        + (0.44 * CAST(ctx.team_free_throws_attempted_total AS double))
                        + CAST(ctx.team_turnovers_total AS double)
                    )
                ) AS expected_usage_percentage,
                100.0 * CAST(aps.steals_total AS double)
                    / CAST(prov.defensive_possessions_total AS double) AS expected_steal_percentage,
                100.0 * CAST(aps.blocks_total AS double)
                    / CAST(prov.opponent_two_point_attempts_while_on_court_total AS double) AS expected_block_percentage,
                CAST(aps.possessions_total AS double) / 2.0 AS expected_possessions,
                48.0 * (CAST(aps.possessions_total AS double) / 2.0)
                    / (CAST(aps.seconds_played_total AS double) / 60.0) AS expected_pace,
                100.0 * CAST(prov.team_points_for_while_on_court_total AS double)
                    / CAST(prov.offensive_possessions_total AS double) AS expected_offensive_rating,
                100.0 * CAST(prov.team_points_against_while_on_court_total AS double)
                    / CAST(prov.defensive_possessions_total AS double) AS expected_defensive_rating
            FROM "vw_player_season_boxscore_advanced" AS view
            INNER JOIN "agg_player_season" AS aps
                ON view.player_id = aps.person_id
               AND view.season_year = aps.season_year
               AND view.season_type = aps.season_type
            INNER JOIN "vw_player_season_provenance_debug" AS prov
                ON view.player_id = prov.player_id
               AND view.season_year = prov.season_year
               AND view.season_type = prov.season_type
            INNER JOIN player_team_context AS ctx
                ON aps.person_id = ctx.person_id
               AND aps.season_year = ctx.season_year
               AND aps.raw_season_type_code = ctx.raw_season_type_code
            WHERE aps.games_played > 0
              AND aps.seconds_played_total > 0
              AND aps.turnovers_total > 0
              AND aps.field_goals_attempted_total > 0
              AND aps.free_throws_attempted_total > 0
              AND aps.possessions_total > 0
              AND prov.offensive_possessions_total > 0
              AND prov.defensive_possessions_total > 0
              AND aps.blocks_total > 0
              AND prov.opponent_two_point_attempts_while_on_court_total > 0
              AND (
                    aps.field_goals_attempted_total
                    + (0.44 * aps.free_throws_attempted_total)
                    + aps.assists_total
                    + aps.turnovers_total
                  ) > 0
              AND (
                    ctx.team_field_goals_attempted_total
                    + (0.44 * ctx.team_free_throws_attempted_total)
                    + ctx.team_turnovers_total
                  ) > 0
            ORDER BY aps.games_played DESC, aps.person_id
            LIMIT 1
        )
        SELECT
            ABS(assist_ratio - expected_assist_ratio) AS assist_ratio_diff,
            ABS(effective_field_goal_percentage - expected_effective_field_goal_percentage) AS efg_diff,
            ABS(true_shooting_percentage - expected_true_shooting_percentage) AS ts_diff,
            ABS(usage_percentage - expected_usage_percentage) AS usage_diff,
            ABS(steal_percentage - expected_steal_percentage) AS steal_pct_diff,
            ABS(block_percentage - expected_block_percentage) AS block_pct_diff,
            ABS(possessions - expected_possessions) AS possessions_diff,
            ABS(pace - expected_pace) AS pace_diff,
            ABS(offensive_rating - expected_offensive_rating) AS offensive_rating_diff,
            ABS(defensive_rating - expected_defensive_rating) AS defensive_rating_diff,
            ABS(net_rating - (expected_offensive_rating - expected_defensive_rating)) AS net_rating_diff
        FROM candidate
        """
    )
    assert rows, "Expected at least one hand-computed comparison row"
    row = rows[0]
    assert row["assist_ratio_diff"] <= 0.05
    assert row["efg_diff"] <= 0.05
    assert row["ts_diff"] <= 0.05
    assert row["usage_diff"] <= 0.05
    assert row["steal_pct_diff"] <= 0.05
    assert row["block_pct_diff"] <= 0.05
    assert row["possessions_diff"] <= 0.05
    assert row["pace_diff"] <= 0.05
    assert row["offensive_rating_diff"] <= 0.05
    assert row["defensive_rating_diff"] <= 0.05
    assert row["net_rating_diff"] <= 0.05
