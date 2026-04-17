from __future__ import annotations

from pipelines.athena.transform.gold import deploy_team_season_boxscore_advanced_view as views


def test_build_view_sql_includes_supported_team_context_sources():
    sql = views.build_view_sql("vw_team_season_boxscore_advanced")

    assert 'CREATE OR REPLACE VIEW "vw_team_season_boxscore_advanced"' in sql
    assert '"agg_team_season"' in sql
    assert '"fct_team_game"' in sql
    assert '"dim_team"' in sql
    assert '"boxscore_team_game"' in sql
    assert '"team_game_context"' in sql
    assert '"season_boxscore_context"' in sql
    assert '"season_type"' in sql
    assert '"ats"."possessions_total"' in sql
    assert '"ats"."defensive_possessions_total"' in sql
    assert '"ats"."opponent_two_point_attempts_total"' in sql
    assert '"offensive_rating"' in sql
    assert '"steal_percentage"' in sql
    assert '"block_percentage"' in sql
    assert '"pie"' in sql
    assert '"three_point_attempt_rate"' in sql
    assert '"free_throw_attempt_rate"' in sql
    assert '"team_season_percentiles"' in sql
    assert '"offensive_rating_percentile"' in sql
    assert '"pie_percentile"' in sql
    assert '"win_percentage_percentile"' not in sql
    assert '"ats"."raw_season_type_code" AS "raw_season_type_code"' not in sql


def test_build_view_sql_aligns_full_possession_family_to_hybrid_possessions():
    sql = views.build_view_sql("vw_team_season_boxscore_advanced")

    hybrid_denominator = '(CAST(COALESCE("ats"."possessions_total", 0) AS double) / 2.0)'
    assert f'CAST("ats"."turnovers_total" AS double) * 100.0 / {hybrid_denominator}' in sql
    assert f'{hybrid_denominator} * 240.0 / (CAST("ats"."seconds_played_total" AS double) / 60.0)' in sql
    assert f'CAST("ats"."points_for_total" AS double) * 100.0 / {hybrid_denominator}' in sql
    assert f'CAST("ats"."points_against_total" AS double) * 100.0 / {hybrid_denominator}' in sql


def test_build_view_sql_uses_canonical_team_denominators_for_steal_and_block_percentage():
    sql = views.build_view_sql("vw_team_season_boxscore_advanced")

    assert 'CAST("ats"."steals_total" AS double) * 100.0' in sql
    assert '/ CAST("ats"."defensive_possessions_total" AS double)' in sql
    assert 'CAST("ats"."blocks_total" AS double) * 100.0' in sql
    assert '/ CAST("ats"."opponent_two_point_attempts_total" AS double)' in sql


def test_build_view_sql_computes_attempt_rates_from_team_season_totals_with_null_zero_fga():
    sql = views.build_view_sql("vw_team_season_boxscore_advanced")

    assert 'CASE WHEN COALESCE("ats"."field_goals_attempted_total", 0) > 0' in sql
    assert 'THEN ROUND(' in sql
    assert 'CAST("ats"."three_pointers_attempted_total" AS double)' in sql
    assert '/ CAST("ats"."field_goals_attempted_total" AS double),\n        3' in sql
    assert 'END AS "three_point_attempt_rate"' in sql
    assert 'CAST("ats"."free_throws_attempted_total" AS double)' in sql
    assert '/ CAST("ats"."field_goals_attempted_total" AS double),\n        3' in sql
    assert 'END AS "free_throw_attempt_rate"' in sql


def test_build_view_sql_can_skip_percentile_projection_for_sidecar_bootstrap():
    sql = views.build_view_sql("vw_team_season_boxscore_advanced", include_percentiles=False)

    assert '"team_season_percentiles"' not in sql
    assert '"offensive_rating_percentile"' not in sql


def test_build_view_sql_casts_numeric_gameid_before_substring_operations():
    sql = views.build_view_sql("vw_team_season_boxscore_advanced", include_percentiles=False)

    assert 'LPAD(CAST("gameid" AS varchar), 10, \'0\') AS "game_id"' in sql
    assert 'SUBSTR(LPAD(CAST("gameid" AS varchar), 10, \'0\'), 1, 3) AS "raw_season_type_code"' in sql
    assert 'CAST(SUBSTR(LPAD(CAST("gameid" AS varchar), 10, \'0\'), 4, 2) AS integer)' in sql
