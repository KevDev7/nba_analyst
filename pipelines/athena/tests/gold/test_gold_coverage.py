from __future__ import annotations

import pytest


NON_NULL_SEASON_QUERIES = {
    "dim_game": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."dim_game"
        WHERE SUBSTR(game_id, 1, 3) = '002'
          AND season_year IS NULL
    """,
    "fct_team_game": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."fct_team_game"
        WHERE SUBSTR(game_id, 1, 3) = '002'
          AND season_year IS NULL
    """,
    "fct_player_game": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."fct_player_game"
        WHERE SUBSTR(game_id, 1, 3) = '002'
          AND season_year IS NULL
    """,
}

NON_NULL_SEASON_TYPE_QUERIES = {
    "dim_game": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."dim_game"
        WHERE SUBSTR(game_id, 1, 3) = '002'
          AND (raw_season_type_code IS NULL OR season_type IS NULL)
    """,
    "fct_team_game": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."fct_team_game"
        WHERE SUBSTR(game_id, 1, 3) = '002'
          AND (raw_season_type_code IS NULL OR season_type IS NULL)
    """,
    "fct_player_game": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."fct_player_game"
        WHERE SUBSTR(game_id, 1, 3) = '002'
          AND (raw_season_type_code IS NULL OR season_type IS NULL)
    """,
}

HISTORICAL_COVERAGE_QUERIES = {
    "dim_game": """
        SELECT COUNT(*) AS row_count
        FROM "{database}"."dim_game"
        WHERE season_year = '2024-25'
    """,
    "fct_team_game": """
        SELECT COUNT(*) AS row_count
        FROM "{database}"."fct_team_game"
        WHERE season_year = '2024-25'
    """,
    "fct_player_game": """
        SELECT COUNT(*) AS row_count
        FROM "{database}"."fct_player_game"
        WHERE season_year = '2024-25'
    """,
}

FOREIGN_KEY_PRESENCE_QUERIES = {
    "fct_player_game.player_sk": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."fct_player_game"
        WHERE person_id IS NOT NULL
          AND player_sk IS NULL
    """,
    "fct_team_game.team_sk": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."fct_team_game"
        WHERE team_id IS NOT NULL
          AND team_sk IS NULL
    """,
    "fct_team_game.opponent_team_sk": """
        SELECT COUNT(*) AS bad_rows
        FROM "{database}"."fct_team_game"
        WHERE opponent_team_id IS NOT NULL
          AND opponent_team_sk IS NULL
    """,
}

PLAYOFF_COVERAGE_QUERIES = {
    "agg_player_season": """
        SELECT COUNT(*) AS row_count
        FROM "{database}"."agg_player_season"
        WHERE raw_season_type_code = '004'
    """,
    "agg_team_season": """
        SELECT COUNT(*) AS row_count
        FROM "{database}"."agg_team_season"
        WHERE raw_season_type_code = '004'
    """,
    "dim_game": """
        SELECT COUNT(*) AS row_count
        FROM "{database}"."dim_game"
        WHERE raw_season_type_code = '004'
    """,
    "fct_player_game": """
        SELECT COUNT(*) AS row_count
        FROM "{database}"."fct_player_game"
        WHERE raw_season_type_code = '004'
    """,
    "fct_team_game": """
        SELECT COUNT(*) AS row_count
        FROM "{database}"."fct_team_game"
        WHERE raw_season_type_code = '004'
    """,
}

EXPECTED_COMPLETED_REGULAR_SEASON_GAME_COUNTS = {
    "2020-21": 1080,
    "2021-22": 1230,
    "2022-23": 1230,
    "2023-24": 1230,
    "2024-25": 1230,
}

EXPECTED_COMPLETED_REGULAR_SEASON_TEAM_GAMES = {
    "2020-21": 72,
    "2021-22": 82,
    "2022-23": 82,
    "2023-24": 82,
    "2024-25": 82,
}

TEAM_CONTEXT_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."dim_team"
    WHERE team_id IN (
      1610612737, 1610612738, 1610612751, 1610612766, 1610612741,
      1610612739, 1610612765, 1610612754, 1610612748, 1610612749,
      1610612752, 1610612753, 1610612755, 1610612761, 1610612764,
      1610612742, 1610612743, 1610612744, 1610612745, 1610612746,
      1610612747, 1610612763, 1610612750, 1610612740, 1610612760,
      1610612756, 1610612757, 1610612758, 1610612759, 1610612762
    )
      AND is_current = 1
      AND (conference IS NULL OR division IS NULL)
"""

POSITION_GROUP_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."dim_player" AS dp
    INNER JOIN "{database}"."extended_player_dim" AS epd
      ON dp.person_id = epd.person_id
    WHERE dp.primary_position IS NOT NULL
      AND (epd.position_group IS NULL OR epd.position_group = '')
"""

CURRENT_POSITION_SURVIVORSHIP_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."dim_player" AS current_row
    WHERE current_row.is_current = 1
      AND current_row.latest_nba_team_id IS NOT NULL
      AND current_row.primary_position IS NULL
      AND EXISTS (
        SELECT 1
        FROM "{database}"."dim_player" AS history_row
        WHERE history_row.person_id = current_row.person_id
          AND history_row.primary_position IS NOT NULL
      )
"""

NBA_LATEST_TEAM_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."dim_player"
    WHERE is_current = 1
      AND latest_nba_team_id IS NULL
      AND latest_team_id IN (
        SELECT team_id
        FROM "{database}"."dim_team"
        WHERE is_current = 1
          AND conference IS NOT NULL
      )
"""

PRIMARY_TEAM_FIELDS_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."agg_player_season"
    WHERE season_type = 'regular_season'
      AND games_played > 0
      AND (
        primary_team_id IS NULL
        OR primary_team_abbreviation IS NULL
        OR primary_team_name IS NULL
      )
"""

PLAYER_GAME_MINUTES_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."fct_player_game"
    WHERE did_play = 1
      AND COALESCE(minutes_calculated_raw, minutes_raw) IS NOT NULL
      AND minutes_played_decimal IS NULL
"""

ONCOURT_NULL_OUTSIDE_2019_20_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."fct_player_game"
    WHERE is_on_court IS NULL
      AND season_year <> '2019-20'
"""

KNOWN_PLAYER_TEAM_REGRESSION_QUERY = """
    SELECT dp.display_name, aps.primary_team_abbreviation
    FROM "{database}"."agg_player_season" AS aps
    LEFT JOIN "{database}"."dim_player" AS dp
      ON aps.current_player_sk = dp.player_sk
    WHERE aps.season_year = '2024-25'
      AND aps.season_type = 'regular_season'
      AND dp.display_name IN ('Shai Gilgeous-Alexander', 'Anthony Edwards')
"""

NO_ZERO_TEAM_ID_PLACEHOLDER_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."dim_game"
    WHERE home_team_id = 0
       OR away_team_id = 0
"""

BROKEN_SHELL_GAME_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."dim_game"
    WHERE game_id IN ('0012200069', '0012200070')
"""

LOCAL_GAME_DATE_REGRESSION_QUERY = """
    SELECT
      dg.game_id,
      CAST(dg.game_date AS VARCHAR) AS dim_game_date,
      CAST(fpg.game_date AS VARCHAR) AS fct_player_game_date,
      CAST(ftg.game_date AS VARCHAR) AS fct_team_game_date
    FROM "{database}"."dim_game" AS dg
    LEFT JOIN "{database}"."fct_player_game" AS fpg
      ON dg.game_id = fpg.game_id
     AND fpg.person_id = 201939
    LEFT JOIN "{database}"."fct_team_game" AS ftg
      ON dg.game_id = ftg.game_id
     AND ftg.team_id = 1610612744
    WHERE dg.game_id = '0042200236'
    LIMIT 1
"""

NON_POSITIVE_NBA_WEEK_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."dim_date"
    WHERE nba_week_number <= 0
"""

NBA_WEEK_NAME_WITHOUT_VALID_NUMBER_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."dim_date"
    WHERE nba_week_name IS NOT NULL
      AND (nba_week_number IS NULL OR nba_week_number <= 0)
"""

PLAYER_PER_GAME_NULL_WITH_PLAYED_GAMES_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."agg_player_season"
    WHERE games_played > 0
      AND (
        points_per_game IS NULL
        OR assists_per_game IS NULL
        OR rebounds_per_game IS NULL
        OR seconds_played_average IS NULL
      )
"""

PLAYER_PERCENTAGE_NULL_WITH_ATTEMPTS_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."agg_player_season"
    WHERE (field_goals_attempted_total > 0 AND field_goals_percentage IS NULL)
       OR (three_pointers_attempted_total > 0 AND three_pointers_percentage IS NULL)
       OR (free_throws_attempted_total > 0 AND free_throws_percentage IS NULL)
"""

PLAYER_PER_GAME_NULL_WITH_ZERO_GAMES_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."agg_player_season"
    WHERE games_played = 0
      AND (
        points_per_game IS NOT NULL
        OR assists_per_game IS NOT NULL
        OR rebounds_per_game IS NOT NULL
        OR seconds_played_average IS NOT NULL
      )
"""

PLAYER_PERCENTAGE_NON_NULL_WITH_ZERO_ATTEMPTS_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."agg_player_season"
    WHERE (field_goals_attempted_total = 0 AND field_goals_percentage IS NOT NULL)
       OR (three_pointers_attempted_total = 0 AND three_pointers_percentage IS NOT NULL)
       OR (free_throws_attempted_total = 0 AND free_throws_percentage IS NOT NULL)
"""

TEAM_ZERO_HOME_AWAY_GAMES_IN_REGULAR_SEASON_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."agg_team_season"
    WHERE season_type = 'regular_season'
      AND (home_games = 0 OR away_games = 0)
"""

TEAM_ZERO_WIN_PCT_WITH_WINS_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."agg_team_season"
    WHERE win_percentage = 0
      AND wins > 0
"""

TEAM_ZERO_POINT_DIFF_PER_GAME_WITH_NONZERO_TOTAL_QUERY = """
    SELECT COUNT(*) AS bad_rows
    FROM "{database}"."agg_team_season"
    WHERE point_differential_per_game = 0
      AND point_diff_total <> 0
"""


@pytest.mark.parametrize("table_name", sorted(NON_NULL_SEASON_QUERIES))
def test_regular_season_rows_have_non_null_season_year(athena_client, athena_settings, table_name: str):
    _, rows = athena_client.execute(NON_NULL_SEASON_QUERIES[table_name].format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, f"{table_name} still has regular-season rows without season_year"


@pytest.mark.parametrize("table_name", sorted(NON_NULL_SEASON_TYPE_QUERIES))
def test_regular_season_rows_have_non_null_season_type_fields(athena_client, athena_settings, table_name: str):
    _, rows = athena_client.execute(NON_NULL_SEASON_TYPE_QUERIES[table_name].format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, f"{table_name} still has regular-season rows without season type metadata"


@pytest.mark.parametrize("table_name", sorted(HISTORICAL_COVERAGE_QUERIES))
def test_historical_2024_25_coverage_exists_for_game_level_tables(athena_client, athena_settings, table_name: str):
    _, rows = athena_client.execute(HISTORICAL_COVERAGE_QUERIES[table_name].format(database=athena_settings.database))
    assert rows[0]["row_count"] > 0, f"{table_name} has no 2024-25 coverage"


@pytest.mark.parametrize("table_name", sorted(PLAYOFF_COVERAGE_QUERIES))
def test_playoff_coverage_exists_for_iteration_2_tables(athena_client, athena_settings, table_name: str):
    _, rows = athena_client.execute(PLAYOFF_COVERAGE_QUERIES[table_name].format(database=athena_settings.database))
    assert rows[0]["row_count"] > 0, f"{table_name} has no playoff coverage"


@pytest.mark.parametrize("label", sorted(FOREIGN_KEY_PRESENCE_QUERIES))
def test_game_level_surrogate_keys_resolve_for_populated_fact_rows(athena_client, athena_settings, label: str):
    _, rows = athena_client.execute(FOREIGN_KEY_PRESENCE_QUERIES[label].format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, f"{label} has unresolved surrogate keys"


def test_current_nba_teams_have_conference_and_division(athena_client, athena_settings):
    _, rows = athena_client.execute(TEAM_CONTEXT_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Current NBA teams are missing conference/division metadata"


def test_players_with_raw_positions_have_normalized_position_groups(athena_client, athena_settings):
    _, rows = athena_client.execute(POSITION_GROUP_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Players with raw positions are missing normalized position groups"


def test_current_players_do_not_forget_previously_known_positions(athena_client, athena_settings):
    _, rows = athena_client.execute(CURRENT_POSITION_SURVIVORSHIP_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Current NBA player rows should carry forward previously known positions"


def test_current_players_keep_latest_nba_team_id_when_latest_team_is_nba(athena_client, athena_settings):
    _, rows = athena_client.execute(NBA_LATEST_TEAM_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Current players on NBA franchises are missing latest_nba_team_id"


def test_regular_season_player_aggregates_expose_primary_team_fields(athena_client, athena_settings):
    _, rows = athena_client.execute(PRIMARY_TEAM_FIELDS_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Regular-season player aggregates are missing primary team identity"


def test_played_player_games_with_raw_minutes_have_normalized_minutes_decimal(athena_client, athena_settings):
    _, rows = athena_client.execute(PLAYER_GAME_MINUTES_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Played player-game rows with raw minutes should expose normalized minutes_played_decimal"


def test_oncourt_nulls_are_confined_to_legacy_2019_20_rows(athena_client, athena_settings):
    _, rows = athena_client.execute(ONCOURT_NULL_OUTSIDE_2019_20_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 223, (
        "Null is_on_court values outside 2019-20 should match the current Databricks-supported "
        "legacy gap count"
    )


def test_known_player_team_regressions_resolve_to_nba_teams(athena_client, athena_settings):
    _, rows = athena_client.execute(KNOWN_PLAYER_TEAM_REGRESSION_QUERY.format(database=athena_settings.database))
    actual = {row["display_name"]: row["primary_team_abbreviation"] for row in rows}
    assert actual.get("Shai Gilgeous-Alexander") == "OKC"
    assert actual.get("Anthony Edwards") == "MIN"


def test_dim_game_does_not_preserve_zero_team_id_placeholders(athena_client, athena_settings):
    _, rows = athena_client.execute(NO_ZERO_TEAM_ID_PLACEHOLDER_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "dim_game should treat 0 team IDs as unresolved placeholders, not real teams"


def test_dim_game_excludes_known_broken_shell_rows(athena_client, athena_settings):
    _, rows = athena_client.execute(BROKEN_SHELL_GAME_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "dim_game should not keep shell games without usable date/time/team identity"


def test_known_playoff_game_uses_local_basketball_date_in_dim_and_facts(athena_client, athena_settings):
    _, rows = athena_client.execute(LOCAL_GAME_DATE_REGRESSION_QUERY.format(database=athena_settings.database))
    assert rows, "Expected playoff date regression row was not returned"
    row = rows[0]
    assert row["dim_game_date"] == "2023-05-12"
    assert row["fct_player_game_date"] == "2023-05-12"
    assert row["fct_team_game_date"] == "2023-05-12"


def test_dim_date_does_not_use_non_positive_nba_week_numbers(athena_client, athena_settings):
    _, rows = athena_client.execute(NON_POSITIVE_NBA_WEEK_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "dim_date should use positive NBA week numbers or NULL, never week 0/negative"


def test_dim_date_named_nba_weeks_require_valid_positive_week_number(athena_client, athena_settings):
    _, rows = athena_client.execute(NBA_WEEK_NAME_WITHOUT_VALID_NUMBER_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "dim_date should not expose nba_week_name without a valid positive nba_week_number"


def test_player_season_per_game_metrics_require_games_played(athena_client, athena_settings):
    _, rows = athena_client.execute(PLAYER_PER_GAME_NULL_WITH_PLAYED_GAMES_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Player per-game aggregates should be populated when games_played > 0"


def test_player_season_per_game_metrics_stay_null_without_games_played(athena_client, athena_settings):
    _, rows = athena_client.execute(PLAYER_PER_GAME_NULL_WITH_ZERO_GAMES_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Player per-game aggregates should stay NULL when games_played = 0"


def test_player_season_percentages_require_attempts(athena_client, athena_settings):
    _, rows = athena_client.execute(PLAYER_PERCENTAGE_NULL_WITH_ATTEMPTS_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Player shooting percentages should be populated when attempts totals are positive"


def test_player_season_percentages_stay_null_without_attempts(athena_client, athena_settings):
    _, rows = athena_client.execute(PLAYER_PERCENTAGE_NON_NULL_WITH_ZERO_ATTEMPTS_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Player shooting percentages should stay NULL when attempts totals are zero"


def test_regular_season_team_aggregates_have_both_home_and_away_games(athena_client, athena_settings):
    _, rows = athena_client.execute(TEAM_ZERO_HOME_AWAY_GAMES_IN_REGULAR_SEASON_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Regular-season team aggregates should not have zero home or away games"


def test_team_win_percentage_zero_only_when_team_has_no_wins(athena_client, athena_settings):
    _, rows = athena_client.execute(TEAM_ZERO_WIN_PCT_WITH_WINS_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Team win_percentage should not be zero when the team has wins"


def test_team_point_differential_per_game_zero_only_when_total_point_diff_is_zero(athena_client, athena_settings):
    _, rows = athena_client.execute(TEAM_ZERO_POINT_DIFF_PER_GAME_WITH_NONZERO_TOTAL_QUERY.format(database=athena_settings.database))
    assert rows[0]["bad_rows"] == 0, "Team point_differential_per_game should only be zero when total point_diff is zero"


@pytest.mark.parametrize(
    ("season_year", "expected_games"),
    sorted(EXPECTED_COMPLETED_REGULAR_SEASON_GAME_COUNTS.items()),
)
def test_completed_regular_seasons_have_expected_game_counts(athena_client, athena_settings, season_year: str, expected_games: int):
    _, rows = athena_client.execute(
        f"""
        SELECT COUNT(*) AS row_count
        FROM "{athena_settings.database}"."dim_game"
        WHERE season_year = '{season_year}'
          AND season_type = 'regular_season'
        """
    )
    assert rows[0]["row_count"] == expected_games, f"{season_year} regular season should have {expected_games} games"


@pytest.mark.parametrize(
    ("season_year", "expected_games_played"),
    sorted(EXPECTED_COMPLETED_REGULAR_SEASON_TEAM_GAMES.items()),
)
def test_completed_regular_seasons_have_expected_team_game_counts(athena_client, athena_settings, season_year: str, expected_games_played: int):
    _, rows = athena_client.execute(
        f"""
        SELECT COUNT(*) AS bad_rows
        FROM "{athena_settings.database}"."agg_team_season"
        WHERE season_year = '{season_year}'
          AND season_type = 'regular_season'
          AND games_played <> {expected_games_played}
        """
    )
    assert rows[0]["bad_rows"] == 0, f"{season_year} regular season teams should all have {expected_games_played} games"
