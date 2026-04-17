from __future__ import annotations

from pipelines.athena.transform.gold import deploy_player_game_shot_type_source_view as views


def test_build_view_sql_includes_serving_columns_and_context_joins() -> None:
    sql = views.build_view_sql("vw_player_game_shot_type_source")

    assert 'CREATE OR REPLACE VIEW "vw_player_game_shot_type_source"' in sql
    assert '"current_player_dim"' in sql
    assert '"fct_player_game_shot_type_source"' in sql
    assert '"dim_game"' in sql
    assert '"dim_player"' in sql
    assert '"player_id"' in sql
    assert '"player_name"' in sql
    assert '"game_id"' in sql
    assert '"game_date"' in sql
    assert '"team"' in sql
    assert '"opponent"' in sql
    assert '"home_away"' in sql
    assert '"shot_type_key"' in sql
    assert '"shot_type"' in sql
    assert '"shot_family"' in sql
    assert '"action_type"' in sql
    assert '"sub_type"' in sql
    assert '"descriptor"' in sql
    assert '"shot_value"' in sql
    assert '"is_two_point_shot"' in sql
    assert '"is_three_point_shot"' in sql
    assert '"field_goals_attempted"' in sql
    assert '"field_goals_made"' in sql
    assert '"three_pointers_attempted"' in sql
    assert '"three_pointers_made"' in sql
    assert '"points_from_field_goals"' in sql
    assert "Re-run deploy_player_game_shot_type_source_view.py" in sql
