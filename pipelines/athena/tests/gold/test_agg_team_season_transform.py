from __future__ import annotations

import math

import pyarrow as pa

from pipelines.athena.transform.gold import transform_to_agg_team_season_parquet as ats


def _table_from_rows(rows: list[dict[str, object]], columns: list[str]) -> pa.Table:
    normalized_rows = [{column: row.get(column) for column in columns} for row in rows]
    return pa.Table.from_pylist(normalized_rows)


def test_build_agg_rows_dedupes_latest_fact_rows_and_rolls_up_team_season() -> None:
    fact_table = _table_from_rows(
        [
            {
                "fct_team_game_sk": 10,
                "game_id": "0022400001",
                "team_id": 1610612737,
                "opponent_team_id": 1610612751,
                "score": 101,
                "opponent_score": 99,
                "point_diff": 2,
                "is_home_team": 1,
                "is_in_bonus": 4,
                "timeouts_remaining": 3,
                "seconds_played_total": 14400.0,
                "assists": 24,
                "blocks": 5,
                "blocks_received": 2,
                "field_goals_attempted": 90,
                "field_goals_made": 40,
                "fouls_offensive": 2,
                "fouls_drawn": 5,
                "fouls_personal": 18,
                "fouls_technical": 0,
                "free_throws_attempted": 18,
                "free_throws_made": 15,
                "rebounds_defensive": 30,
                "rebounds_offensive": 10,
                "rebounds_total": 40,
                "steals": 8,
                "turnovers": 11,
                "three_pointers_attempted": 30,
                "three_pointers_made": 10,
                "two_pointers_attempted": 60,
                "two_pointers_made": 30,
                "points_fast_break": 12,
                "points_in_the_paint": 42,
                "points_second_chance": 8,
                "is_win": 1,
                "is_loss": 0,
                "is_tie": 0,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "updated_at_utc": "2025-01-01T00:00:00Z",
            },
            {
                "fct_team_game_sk": 11,
                "game_id": "0022400001",
                "team_id": 1610612737,
                "opponent_team_id": 1610612751,
                "score": 102,
                "opponent_score": 99,
                "point_diff": 3,
                "is_home_team": 1,
                "is_in_bonus": 5,
                "timeouts_remaining": 2,
                "seconds_played_total": 14400.0,
                "assists": 25,
                "blocks": 6,
                "blocks_received": 2,
                "field_goals_attempted": 91,
                "field_goals_made": 41,
                "fouls_offensive": 2,
                "fouls_drawn": 5,
                "fouls_personal": 17,
                "fouls_technical": 0,
                "free_throws_attempted": 20,
                "free_throws_made": 16,
                "rebounds_defensive": 31,
                "rebounds_offensive": 10,
                "rebounds_total": 41,
                "steals": 8,
                "turnovers": 10,
                "three_pointers_attempted": 31,
                "three_pointers_made": 11,
                "two_pointers_attempted": 60,
                "two_pointers_made": 30,
                "points_fast_break": 12,
                "points_in_the_paint": 44,
                "points_second_chance": 8,
                "is_win": 1,
                "is_loss": 0,
                "is_tie": 0,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "updated_at_utc": "2025-01-02T00:00:00Z",
            },
            {
                "fct_team_game_sk": 12,
                "game_id": "0022400002",
                "team_id": 1610612737,
                "opponent_team_id": 1610612748,
                "score": 95,
                "opponent_score": 100,
                "point_diff": -5,
                "is_home_team": 0,
                "is_in_bonus": 3,
                "timeouts_remaining": 4,
                "seconds_played_total": 14400.0,
                "assists": 20,
                "blocks": 4,
                "blocks_received": 3,
                "field_goals_attempted": 88,
                "field_goals_made": 36,
                "fouls_offensive": 1,
                "fouls_drawn": 6,
                "fouls_personal": 19,
                "fouls_technical": 1,
                "free_throws_attempted": 14,
                "free_throws_made": 11,
                "rebounds_defensive": 29,
                "rebounds_offensive": 9,
                "rebounds_total": 38,
                "steals": 6,
                "turnovers": 12,
                "three_pointers_attempted": 28,
                "three_pointers_made": 9,
                "two_pointers_attempted": 60,
                "two_pointers_made": 27,
                "points_fast_break": 9,
                "points_in_the_paint": 38,
                "points_second_chance": 7,
                "is_win": 0,
                "is_loss": 1,
                "is_tie": 0,
                "season_year": "2024-25",
                "season_start_year": 2024,
                "raw_season_type_code": "002",
                "season_type": "regular_season",
                "updated_at_utc": "2025-01-03T00:00:00Z",
            },
        ],
        ats.FACT_REQUIRED_COLUMNS,
    )

    rows = ats.build_agg_rows(
        fact_table,
        current_team_sk_map={1610612737: 7001},
        team_game_possession_map={
            ("0022400001", 1610612737): {
                "exact_possession_games": 1,
                "ot_fallback_possession_games": 0,
                "event_estimated_possession_games": 0,
                "boxscore_estimated_possession_games": 0,
                "missing_possession_games": 0,
                "offensive_possessions_total": 101.0,
                "defensive_possessions_total": 99.0,
            },
            ("0022400002", 1610612737): {
                "exact_possession_games": 0,
                "ot_fallback_possession_games": 0,
                "event_estimated_possession_games": 1,
                "boxscore_estimated_possession_games": 0,
                "missing_possession_games": 0,
                "offensive_possessions_total": 98.0,
                "defensive_possessions_total": 100.0,
            },
        },
        team_game_shot_context_map={
            ("0022400001", 1610612737): {
                "exact_shot_context_games": 1,
                "event_estimated_shot_context_games": 0,
                "boxscore_estimated_shot_context_games": 0,
                "missing_shot_context_games": 0,
                "opponent_two_point_attempts_total": 58.0,
            },
            ("0022400002", 1610612737): {
                "exact_shot_context_games": 0,
                "event_estimated_shot_context_games": 1,
                "boxscore_estimated_shot_context_games": 0,
                "missing_shot_context_games": 0,
                "opponent_two_point_attempts_total": 55.0,
            },
        },
    )

    assert len(rows) == 1
    row = rows[0]

    assert row["team_id"] == 1610612737
    assert row["current_team_sk"] == 7001
    assert row["season_year"] == "2024-25"
    assert row["season_start_year"] == 2024
    assert row["games_played"] == 2
    assert row["wins"] == 1
    assert row["losses"] == 1
    assert row["ties"] == 0
    assert row["home_games"] == 1
    assert row["away_games"] == 1
    assert row["home_wins"] == 1
    assert row["away_wins"] == 0
    assert row["distinct_opponent_count"] == 2
    assert row["points_for_total"] == 197
    assert row["points_against_total"] == 199
    assert row["point_diff_total"] == -2
    assert row["assists_total"] == 45
    assert row["field_goals_made_total"] == 77
    assert row["field_goals_attempted_total"] == 179
    assert math.isclose(row["win_percentage"], 0.5)
    assert math.isclose(row["points_for_per_game"], 98.5)
    assert math.isclose(row["points_against_per_game"], 99.5)
    assert math.isclose(row["point_differential_per_game"], -1.0)
    assert math.isclose(row["field_goals_percentage"], 77 / 179)
    assert math.isclose(row["three_pointers_percentage"], 20 / 59)
    assert math.isclose(row["two_pointers_percentage"], 57 / 120)
    assert row["exact_possession_games"] == 1
    assert row["event_estimated_possession_games"] == 1
    assert row["boxscore_estimated_possession_games"] == 0
    assert math.isclose(row["offensive_possessions_total"], 199.0)
    assert math.isclose(row["defensive_possessions_total"], 199.0)
    assert math.isclose(row["possessions_total"], 398.0)
    assert row["exact_shot_context_games"] == 1
    assert row["event_estimated_shot_context_games"] == 1
    assert row["boxscore_estimated_shot_context_games"] == 0
    assert row["missing_shot_context_games"] == 0
    assert math.isclose(row["opponent_two_point_attempts_total"], 113.0)

    public_rows = ats.build_public_rows(rows)
    provenance_rows = ats.build_provenance_sidecar_rows(rows)

    assert len(public_rows) == 1
    assert len(provenance_rows) == 1
    assert "exact_possession_games" not in public_rows[0]
    assert "missing_shot_context_games" not in public_rows[0]
    assert "exact_possession_games" in provenance_rows[0]
    assert "missing_shot_context_games" in provenance_rows[0]
    assert "points_for_total" not in provenance_rows[0]


def test_build_team_game_defensive_shot_context_map_from_table_uses_canonical_silver_rows() -> None:
    context_table = _table_from_rows(
        [
            {
                "game_id": "0022400001",
                "team_id": 1610612737,
                "exact_game_flag": 1,
                "event_estimated_game_flag": 0,
                "boxscore_estimated_game_flag": 0,
                "missing_game_flag": 0,
                "opponent_two_point_attempts": 58.0,
            }
        ],
        ats.TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS,
    )

    shot_context_map = ats.build_team_game_defensive_shot_context_map_from_table(context_table)

    assert shot_context_map[("0022400001", 1610612737)] == {
        "exact_shot_context_games": 1,
        "event_estimated_shot_context_games": 0,
        "boxscore_estimated_shot_context_games": 0,
        "missing_shot_context_games": 0,
        "opponent_two_point_attempts_total": 58.0,
    }
