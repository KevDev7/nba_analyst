from __future__ import annotations


EXPECTED_COLUMNS = [
    "player_id",
    "player_name",
    "season_year",
    "season_type",
    "team",
    "exact_possession_games",
    "ot_fallback_possession_games",
    "event_estimated_possession_games",
    "boxscore_estimated_possession_games",
    "missing_possession_games",
    "possession_coverage_pct",
    "possession_source_method",
    "exact_shot_context_games",
    "event_estimated_shot_context_games",
    "boxscore_estimated_shot_context_games",
    "missing_shot_context_games",
    "shot_context_coverage_pct",
    "shot_context_source_method",
    "offensive_possessions_total",
    "defensive_possessions_total",
    "possessions_total",
    "team_points_for_while_on_court_total",
    "team_points_against_while_on_court_total",
    "opponent_two_point_attempts_while_on_court_total",
]


def test_player_season_provenance_debug_view_exposes_expected_columns(athena_client):
    headers, _ = athena_client.execute(
        """
        SELECT *
        FROM "vw_player_season_provenance_debug"
        LIMIT 1
        """
    )
    assert headers == EXPECTED_COLUMNS


def test_player_season_provenance_debug_view_is_queryable_and_non_empty(athena_client):
    _, rows = athena_client.execute(
        """
        SELECT COUNT(*) AS row_count
        FROM "vw_player_season_provenance_debug"
        """
    )
    assert rows[0]["row_count"] > 0
