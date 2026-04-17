from __future__ import annotations

import pytest


GRAIN_QUERIES = {
    "dim_game": """
        SELECT
          COUNT(*) AS total_rows,
          COUNT(DISTINCT game_id) AS distinct_rows
        FROM "{database}"."dim_game"
    """,
    "fct_team_game": """
        SELECT
          COUNT(*) AS total_rows,
          COUNT(DISTINCT game_id || '|' || CAST(team_id AS VARCHAR)) AS distinct_rows
        FROM "{database}"."fct_team_game"
    """,
    "fct_player_game": """
        SELECT
          COUNT(*) AS total_rows,
          COUNT(DISTINCT game_id || '|' || CAST(person_id AS VARCHAR)) AS distinct_rows
        FROM "{database}"."fct_player_game"
    """,
    "agg_team_season": """
        SELECT
          COUNT(*) AS total_rows,
          COUNT(DISTINCT CAST(team_id AS VARCHAR) || '|' || season_year || '|' || raw_season_type_code) AS distinct_rows
        FROM "{database}"."agg_team_season"
    """,
    "agg_player_season": """
        SELECT
          COUNT(*) AS total_rows,
          COUNT(DISTINCT CAST(person_id AS VARCHAR) || '|' || season_year || '|' || raw_season_type_code) AS distinct_rows
        FROM "{database}"."agg_player_season"
    """,
}


@pytest.mark.parametrize("table_name", sorted(GRAIN_QUERIES))
def test_gold_tables_preserve_expected_grain(athena_client, athena_settings, table_name: str):
    _, rows = athena_client.execute(GRAIN_QUERIES[table_name].format(database=athena_settings.database))
    assert rows, f"{table_name} returned no grain result"
    row = rows[0]
    assert row["total_rows"] > 0, f"{table_name} should not be empty"
    assert row["total_rows"] == row["distinct_rows"], (
        f"{table_name} violates its expected grain: total_rows={row['total_rows']} "
        f"distinct_rows={row['distinct_rows']}"
    )
