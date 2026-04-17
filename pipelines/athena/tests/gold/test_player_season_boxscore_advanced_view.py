from __future__ import annotations

from pipelines.athena.transform.gold import deploy_player_season_boxscore_advanced_view as views


def test_build_view_sql_includes_boxscore_advanced_columns_and_context_ctes():
    sql = views.build_view_sql(
        "vw_player_season_boxscore_advanced",
        [
            ("person_id", "bigint"),
            ("current_player_sk", "bigint"),
            ("season_year", "varchar"),
            ("season_type", "varchar"),
            ("raw_season_type_code", "varchar"),
            ("age_on_jan_31", "bigint"),
            ("primary_team_abbreviation", "varchar"),
            ("games_played", "bigint"),
            ("wins", "bigint"),
            ("losses", "bigint"),
            ("seconds_played_total", "double"),
            ("points_total", "bigint"),
            ("assists_total", "bigint"),
            ("rebounds_total", "bigint"),
            ("rebounds_offensive_total", "bigint"),
            ("rebounds_defensive_total", "bigint"),
            ("steals_total", "bigint"),
            ("blocks_total", "bigint"),
            ("turnovers_total", "bigint"),
            ("field_goals_made_total", "bigint"),
            ("field_goals_attempted_total", "bigint"),
            ("three_pointers_made_total", "bigint"),
            ("free_throws_made_total", "bigint"),
            ("free_throws_attempted_total", "bigint"),
            ("fouls_personal_total", "bigint"),
            ("possessions_total", "double"),
        ],
    )

    assert 'CREATE OR REPLACE VIEW "vw_player_season_boxscore_advanced"' in sql
    assert '"played_player_games"' in sql
    assert '"player_team_context"' in sql
    assert '"pie_game_totals"' in sql
    assert '"player_pie_context"' in sql
    assert '"current_player_dim"' in sql
    assert '"player_id"' in sql
    assert '"player_name"' in sql
    assert '"ast_to_turnover_ratio"' in sql
    assert '"assist_ratio"' in sql
    assert '"offensive_rebound_percentage"' in sql
    assert '"defensive_rebound_percentage"' in sql
    assert '"rebound_percentage"' in sql
    assert '"turnover_ratio"' in sql
    assert '"effective_field_goal_percentage"' in sql
    assert '"three_point_attempt_rate"' in sql
    assert '"free_throw_attempt_rate"' in sql
    assert '"true_shooting_percentage"' in sql
    assert '"pie"' in sql
    assert '"possessions"' in sql
    assert '"pace"' in sql
    assert '"player_season_percentiles"' in sql
    assert '"minutes_percentile"' in sql
    assert '"block_percentage_percentile"' in sql
    assert '"offensive_rating"' in sql
    assert '"defensive_rating"' in sql
    assert '"net_rating"' in sql
    assert '"assist_percentage"' in sql
    assert '"usage_percentage"' in sql
    assert '"opponent_two_point_attempts_while_on_court_total"' in sql
    assert '"vw_player_season_provenance_debug"' in sql
    assert '"possession_source_method"' not in sql
    assert '"exact_possession_games"' not in sql
    assert '"possession_coverage_pct"' not in sql
    assert '"opponent_two_pointers_attempted_total"' not in sql
    assert '"points_per_game_percentile"' not in sql
    assert 'AS "raw_season_type_code"' not in sql
    assert "Re-run deploy_player_season_boxscore_advanced_view.py" in sql


def test_build_view_sql_computes_attempt_rates_from_season_totals_with_null_zero_fga():
    sql = views.build_view_sql(
        "vw_player_season_boxscore_advanced",
        [
            ("person_id", "bigint"),
            ("current_player_sk", "bigint"),
            ("season_year", "varchar"),
            ("season_type", "varchar"),
            ("raw_season_type_code", "varchar"),
            ("age_on_jan_31", "bigint"),
            ("primary_team_abbreviation", "varchar"),
            ("games_played", "bigint"),
            ("wins", "bigint"),
            ("losses", "bigint"),
            ("seconds_played_total", "double"),
            ("points_total", "bigint"),
            ("assists_total", "bigint"),
            ("rebounds_total", "bigint"),
            ("rebounds_offensive_total", "bigint"),
            ("rebounds_defensive_total", "bigint"),
            ("steals_total", "bigint"),
            ("blocks_total", "bigint"),
            ("turnovers_total", "bigint"),
            ("field_goals_made_total", "bigint"),
            ("field_goals_attempted_total", "bigint"),
            ("three_pointers_made_total", "bigint"),
            ("free_throws_made_total", "bigint"),
            ("free_throws_attempted_total", "bigint"),
            ("fouls_personal_total", "bigint"),
            ("possessions_total", "double"),
        ],
    )

    assert 'WHEN COALESCE("aps"."field_goals_attempted_total", 0) > 0' in sql
    assert 'THEN ROUND(' in sql
    assert 'CAST("aps"."three_pointers_attempted_total" AS double)' in sql
    assert '/ CAST("aps"."field_goals_attempted_total" AS double),' in sql
    assert '/ CAST("aps"."field_goals_attempted_total" AS double),\n            3' in sql
    assert 'END AS "three_point_attempt_rate"' in sql
    assert 'CAST("aps"."free_throws_attempted_total" AS double)' in sql
    assert '/ CAST("aps"."field_goals_attempted_total" AS double),\n            3' in sql
    assert 'END AS "free_throw_attempt_rate"' in sql
