from __future__ import annotations

from pipelines.athena.transform.gold import deploy_all_views
from pipelines.athena.transform.gold import athena_view_helpers


def test_supported_deploy_inventory_matches_curated_athena_surface():
    assert deploy_all_views.SUPPORTED_DEPLOYERS == [
        "deploy_player_season_boxscore_advanced_view",
        "deploy_player_game_shot_type_source_view",
        "deploy_team_season_boxscore_advanced_view",
    ]
    assert deploy_all_views.INTERNAL_DEPLOYERS == [
        "deploy_player_season_provenance_debug_view",
    ]
    assert athena_view_helpers.CROSS_BACKEND_SUPPORTED_VIEW_NAMES == [
        "vw_team_season_boxscore_advanced",
    ]
    assert athena_view_helpers.ATHENA_ONLY_SUPPORTED_VIEW_NAMES == [
        "vw_player_season_boxscore_advanced",
        "vw_player_game_shot_type_source",
    ]
    assert athena_view_helpers.SUPPORTED_VIEW_NAMES == (
        athena_view_helpers.CROSS_BACKEND_SUPPORTED_VIEW_NAMES + athena_view_helpers.ATHENA_ONLY_SUPPORTED_VIEW_NAMES
    )


def test_deferred_views_are_explicitly_excluded_from_supported_surface():
    deferred = set(athena_view_helpers.DEFERRED_VIEW_NAMES)
    retired = set(athena_view_helpers.RETIRED_VIEW_NAMES)
    supported = set(athena_view_helpers.SUPPORTED_VIEW_NAMES)
    internal = set(athena_view_helpers.ATHENA_ONLY_INTERNAL_VIEW_NAMES)

    assert deferred == {
        "vw_player_season_pace",
        "vw_player_season_usage",
        "vw_player_season_per_possession",
        "vw_player_season_per_100_possessions",
    }
    assert retired == {
        "vw_team_season_advanced",
        "vw_player_season_rebound_percentages",
        "vw_player_season_pie",
        "vw_player_season_per_minute",
        "vw_player_season_per_30_minutes",
        "vw_player_season_per_40_minutes",
        "vw_player_season_per_48_minutes",
        "vw_player_season_advanced_formulas",
        "vw_player_season_advanced",
    }
    assert deferred.isdisjoint(supported)
    assert retired.isdisjoint(supported)
    assert internal == {
        "vw_player_season_provenance_debug",
    }
    assert internal.isdisjoint(supported)
    assert internal.isdisjoint(deferred)
    assert internal.isdisjoint(retired)


def test_supported_player_agg_public_projection_excludes_internal_provenance_columns():
    selected = athena_view_helpers.select_public_player_agg_columns(
        [
            ("agg_player_season_sk", "bigint"),
            ("person_id", "bigint"),
            ("current_player_sk", "bigint"),
            ("season_year", "varchar"),
            ("season_start_year", "bigint"),
            ("raw_season_type_code", "varchar"),
            ("season_type", "varchar"),
            ("age_on_jan_31", "bigint"),
            ("primary_team_id", "bigint"),
            ("primary_team_abbreviation", "varchar"),
            ("primary_team_name", "varchar"),
            ("is_multi_team_season", "boolean"),
            ("games_on_roster", "bigint"),
            ("games_played", "bigint"),
            ("games_started", "bigint"),
            ("wins", "bigint"),
            ("losses", "bigint"),
            ("team_count", "bigint"),
            ("seconds_played_total", "bigint"),
            ("seconds_played_average", "double"),
            ("minutes_per_game", "double"),
            ("points_total", "bigint"),
            ("assists_total", "bigint"),
            ("rebounds_total", "bigint"),
            ("steals_total", "bigint"),
            ("blocks_total", "bigint"),
            ("turnovers_total", "bigint"),
            ("double_doubles", "bigint"),
            ("triple_doubles", "bigint"),
            ("quadruple_doubles", "bigint"),
            ("field_goals_percentage", "double"),
            ("three_pointers_percentage", "double"),
            ("free_throws_percentage", "double"),
            ("points_per_game", "double"),
            ("assists_per_game", "double"),
            ("rebounds_per_game", "double"),
            ("rebounds_offensive_total", "bigint"),
            ("rebounds_defensive_total", "bigint"),
            ("field_goals_made_total", "bigint"),
            ("field_goals_attempted_total", "bigint"),
            ("three_pointers_made_total", "bigint"),
            ("three_pointers_attempted_total", "bigint"),
            ("free_throws_made_total", "bigint"),
            ("free_throws_attempted_total", "bigint"),
            ("points_fast_break_total", "bigint"),
            ("points_in_the_paint_total", "bigint"),
            ("points_second_chance_total", "bigint"),
            ("fouls_offensive_total", "bigint"),
            ("fouls_drawn_total", "bigint"),
            ("fouls_personal_total", "bigint"),
            ("fouls_technical_total", "bigint"),
            ("raw_plus_value_total", "bigint"),
            ("raw_minus_value_total", "bigint"),
            ("plus_minus_points_total", "bigint"),
            ("possessions_total", "double"),
            ("record_source", "varchar"),
            ("created_at_utc", "timestamp"),
            ("updated_at_utc", "timestamp"),
            ("fantasy_points_total", "double"),
        ]
    )

    assert [column_name for column_name, _ in selected] == athena_view_helpers.PUBLIC_PLAYER_AGG_COLUMNS
    assert "raw_season_type_code" not in [column_name for column_name, _ in selected]


def test_supported_player_agg_internal_projection_keeps_raw_season_code_for_join_context():
    selected = athena_view_helpers.select_internal_player_agg_columns(
        [
            ("agg_player_season_sk", "bigint"),
            ("person_id", "bigint"),
            ("current_player_sk", "bigint"),
            ("season_year", "varchar"),
            ("season_start_year", "bigint"),
            ("raw_season_type_code", "varchar"),
            ("season_type", "varchar"),
            ("age_on_jan_31", "bigint"),
            ("primary_team_id", "bigint"),
            ("primary_team_abbreviation", "varchar"),
            ("primary_team_name", "varchar"),
            ("is_multi_team_season", "boolean"),
            ("games_on_roster", "bigint"),
            ("games_played", "bigint"),
            ("games_started", "bigint"),
            ("wins", "bigint"),
                ("losses", "bigint"),
                ("team_count", "bigint"),
                ("seconds_played_total", "bigint"),
                ("seconds_played_average", "double"),
                ("minutes_per_game", "double"),
                ("points_total", "bigint"),
            ("assists_total", "bigint"),
            ("rebounds_total", "bigint"),
            ("steals_total", "bigint"),
            ("blocks_total", "bigint"),
            ("turnovers_total", "bigint"),
            ("double_doubles", "bigint"),
            ("triple_doubles", "bigint"),
            ("quadruple_doubles", "bigint"),
            ("field_goals_percentage", "double"),
            ("three_pointers_percentage", "double"),
            ("free_throws_percentage", "double"),
            ("points_per_game", "double"),
            ("assists_per_game", "double"),
            ("rebounds_per_game", "double"),
            ("rebounds_offensive_total", "bigint"),
            ("rebounds_defensive_total", "bigint"),
            ("field_goals_made_total", "bigint"),
            ("field_goals_attempted_total", "bigint"),
            ("three_pointers_made_total", "bigint"),
            ("three_pointers_attempted_total", "bigint"),
            ("free_throws_made_total", "bigint"),
            ("free_throws_attempted_total", "bigint"),
            ("points_fast_break_total", "bigint"),
            ("points_in_the_paint_total", "bigint"),
            ("points_second_chance_total", "bigint"),
            ("fouls_offensive_total", "bigint"),
            ("fouls_drawn_total", "bigint"),
            ("fouls_personal_total", "bigint"),
            ("fouls_technical_total", "bigint"),
            ("raw_plus_value_total", "bigint"),
            ("raw_minus_value_total", "bigint"),
            ("plus_minus_points_total", "bigint"),
            ("possessions_total", "double"),
            ("record_source", "varchar"),
            ("created_at_utc", "timestamp"),
            ("updated_at_utc", "timestamp"),
        ]
    )

    assert [column_name for column_name, _ in selected] == athena_view_helpers.INTERNAL_PLAYER_AGG_COLUMNS
    assert "raw_season_type_code" in [column_name for column_name, _ in selected]
