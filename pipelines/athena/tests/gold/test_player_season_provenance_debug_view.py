from __future__ import annotations

from pipelines.athena.transform.gold import deploy_player_season_provenance_debug_view as views


def test_build_view_sql_exposes_expected_internal_provenance_columns():
    sql = views.build_view_sql(
        "vw_player_season_provenance_debug",
        [
            ("person_id", "bigint"),
            ("current_player_sk", "bigint"),
            ("season_year", "varchar"),
            ("raw_season_type_code", "varchar"),
            ("season_type", "varchar"),
            ("primary_team_abbreviation", "varchar"),
            ("primary_team_name", "varchar"),
            ("games_played", "bigint"),
            ("possessions_total", "double"),
        ],
    )

    assert 'CREATE OR REPLACE VIEW "vw_player_season_provenance_debug"' in sql
    assert '"player_id"' in sql
    assert '"player_name"' in sql
    assert '"season_year"' in sql
    assert '"season_type"' in sql
    assert '"team"' in sql
    assert '"exact_possession_games"' in sql
    assert '"ot_fallback_possession_games"' in sql
    assert '"event_estimated_possession_games"' in sql
    assert '"boxscore_estimated_possession_games"' in sql
    assert '"missing_possession_games"' in sql
    assert '"possession_coverage_pct"' in sql
    assert '"possession_source_method"' in sql
    assert '"exact_shot_context_games"' in sql
    assert '"event_estimated_shot_context_games"' in sql
    assert '"boxscore_estimated_shot_context_games"' in sql
    assert '"missing_shot_context_games"' in sql
    assert '"shot_context_coverage_pct"' in sql
    assert '"shot_context_source_method"' in sql
    assert '"offensive_possessions_total"' in sql
    assert '"defensive_possessions_total"' in sql
    assert '"possessions_total"' in sql
    assert '"team_points_for_while_on_court_total"' in sql
    assert '"team_points_against_while_on_court_total"' in sql
    assert '"opponent_two_point_attempts_while_on_court_total"' in sql
