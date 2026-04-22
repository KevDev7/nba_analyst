"""Purpose: Build semantic_gold player_season as a silver-first season aggregate object.
Inputs: Silver player-game rows plus silver game/schedule/team-game context.
Outputs: One semantic player_season row per (person_id, season_year, season_type).
Next file: transform_to_player_season_team_parquet.py provides the player-team-stint companion object.
"""

from __future__ import annotations

from datetime import date

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import (
    S3_BUCKET,
    games_played_from_values,
    parse_date_or_none,
    read_parquet_table_from_s3,
    safe_ratio,
    to_int_or_none,
    to_float_or_none,
    to_positive_int_or_none,
    to_str_or_none,
    season_start_year_from_label,
    write_parquet_to_s3,
)
from pipelines.athena.transform.gold.transform_to_dim_game_parquet import (
    BOXSCORE_REQUIRED_COLUMNS,
    BOXSCORE_SOURCE_KEY,
    SCHEDULE_REQUIRED_COLUMNS,
    SCHEDULE_SOURCE_KEY,
)
from pipelines.athena.transform.gold.transform_to_fct_team_game_parquet import (
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
)
from pipelines.athena.transform.gold.transform_to_fct_player_game_parquet import (
    PLAYER_REQUIRED_COLUMNS,
    PLAYER_SOURCE_KEY,
)
from pipelines.athena.transform.gold.player_surface.history import (
    build_bbr_birth_date_map,
    build_player_bio_map,
    merge_bbr_birth_date_fallbacks,
)
from pipelines.athena.transform.gold.player_surface.sources import (
    BBR_BRIDGE_REQUIRED_COLUMNS,
    BBR_BRIDGE_SOURCE_KEY,
    BBR_PROFILE_REQUIRED_COLUMNS,
    BBR_PROFILE_SOURCE_KEY,
    PLAYER_BIO_REQUIRED_COLUMNS,
    PLAYER_BIO_SOURCE_KEY,
)

from .contracts import PLAYER_SEASON_SCHEMA
from .transform_to_player_game_parquet import (
    TEAM_GAME_USAGE_REQUIRED_COLUMNS,
    TEAM_GAME_USAGE_SOURCE_KEY,
    build_player_game_rows_from_tables,
    build_team_usage_context_map_from_table,
)

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/player_season/player_season.parquet"
PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY = "silver/player_game_possession_context.parquet"
PLAYER_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "offensive_possessions",
    "defensive_possessions",
    "used_offensive_possessions",
    "team_points_for_while_on_court",
    "team_points_against_while_on_court",
]
PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY = "silver/player_game_defensive_shot_context.parquet"
PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "opponent_two_point_attempts_while_on_court",
]
PLAYER_GAME_OPPORTUNITY_CONTEXT_SOURCE_KEY = "silver/player_game_opportunity_context.parquet"
PLAYER_GAME_OPPORTUNITY_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "teammate_field_goals_made_while_on_court",
    "offensive_rebound_opportunities_while_on_court",
    "defensive_rebound_opportunities_while_on_court",
    "rebound_opportunities_while_on_court",
]


def _season_january_thirty_first(season_start_year: int) -> date:
    return date(season_start_year + 1, 1, 31)


def _age_in_completed_years(*, birth_date: date | None, reference_date: date) -> int | None:
    if birth_date is None or birth_date > reference_date:
        return None
    years = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _rounded_ratio(numerator: object, denominator: object, *, scale: float = 1.0) -> float | None:
    ratio = safe_ratio(numerator, denominator)
    if ratio is None:
        return None
    return round(ratio * scale, 1)


def _counted_usage_percentage(
    *,
    offensive_possessions_total: float,
    used_offensive_possessions_total: float | None,
    proxy_player_usage_numerator: float,
) -> float | None:
    if offensive_possessions_total <= 0:
        return None
    if used_offensive_possessions_total is None or used_offensive_possessions_total < 0:
        return None
    if used_offensive_possessions_total > offensive_possessions_total:
        return None
    if used_offensive_possessions_total == 0 and proxy_player_usage_numerator > 0:
        return None
    if proxy_player_usage_numerator > 0 and used_offensive_possessions_total < (0.25 * proxy_player_usage_numerator):
        return None
    return round((used_offensive_possessions_total * 100.0) / offensive_possessions_total, 1)


def _proxy_usage_percentage(
    *,
    player_field_goals_attempted_total: int,
    player_free_throws_attempted_total: int,
    player_turnovers_total: int,
    player_minutes_total: float,
    team_field_goals_attempted_total: int,
    team_free_throws_attempted_total: int,
    team_turnovers_total: int,
    team_minutes_total: float,
) -> float | None:
    if player_minutes_total <= 0 or team_minutes_total <= 0:
        return None
    player_usage_numerator = (
        float(player_field_goals_attempted_total)
        + (0.44 * float(player_free_throws_attempted_total))
        + float(player_turnovers_total)
    )
    team_usage_denominator = (
        float(team_field_goals_attempted_total)
        + (0.44 * float(team_free_throws_attempted_total))
        + float(team_turnovers_total)
    )
    if team_usage_denominator <= 0:
        return None
    return round(
        100.0
        * player_usage_numerator
        * team_minutes_total
        / (team_usage_denominator * 5.0 * player_minutes_total),
        1,
    )


def build_player_birth_date_map_from_tables(
    player_bio_table: pa.Table | None,
    bridge_table: pa.Table | None = None,
    bbr_profile_table: pa.Table | None = None,
) -> dict[int, date]:
    if player_bio_table is None:
        return {}

    player_bio_by_person = merge_bbr_birth_date_fallbacks(
        build_player_bio_map(player_bio_table),
        build_bbr_birth_date_map(bridge_table, bbr_profile_table),
    )
    return {
        person_id: birth_date
        for person_id, attrs in player_bio_by_person.items()
        if isinstance((birth_date := parse_date_or_none(attrs.get("birth_date"))), date)
    }


def build_player_game_possession_context_map_from_table(
    player_game_possession_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, float | None]]:
    if player_game_possession_context_table is None:
        return {}

    possession_context_by_key: dict[tuple[str, int], dict[str, float | None]] = {}
    for row in player_game_possession_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        person_id = to_positive_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None:
            continue
        possession_context_by_key[(game_id, person_id)] = {
            "offensive_possessions": to_float_or_none(row.get("offensive_possessions")),
            "defensive_possessions": to_float_or_none(row.get("defensive_possessions")),
            "used_offensive_possessions": to_float_or_none(row.get("used_offensive_possessions")),
            "team_points_for_while_on_court": to_float_or_none(row.get("team_points_for_while_on_court")),
            "team_points_against_while_on_court": to_float_or_none(row.get("team_points_against_while_on_court")),
        }
    return possession_context_by_key


def build_player_game_defensive_shot_context_map_from_table(
    player_game_defensive_shot_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, float | None]]:
    if player_game_defensive_shot_context_table is None:
        return {}

    shot_context_by_key: dict[tuple[str, int], dict[str, float | None]] = {}
    for row in player_game_defensive_shot_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        person_id = to_positive_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None:
            continue
        shot_context_by_key[(game_id, person_id)] = {
            "opponent_two_point_attempts_while_on_court": to_float_or_none(
                row.get("opponent_two_point_attempts_while_on_court")
            )
        }
    return shot_context_by_key


def build_player_game_opportunity_context_map_from_table(
    player_game_opportunity_context_table: pa.Table | None,
) -> dict[tuple[str, int], dict[str, float | None]]:
    if player_game_opportunity_context_table is None:
        return {}

    opportunity_context_by_key: dict[tuple[str, int], dict[str, float | None]] = {}
    for row in player_game_opportunity_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        person_id = to_positive_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None:
            continue
        opportunity_context_by_key[(game_id, person_id)] = {
            "teammate_field_goals_made_while_on_court": to_float_or_none(
                row.get("teammate_field_goals_made_while_on_court")
            ),
            "offensive_rebound_opportunities_while_on_court": to_float_or_none(
                row.get("offensive_rebound_opportunities_while_on_court")
            ),
            "defensive_rebound_opportunities_while_on_court": to_float_or_none(
                row.get("defensive_rebound_opportunities_while_on_court")
            ),
            "rebound_opportunities_while_on_court": to_float_or_none(
                row.get("rebound_opportunities_while_on_court")
            ),
        }
    return opportunity_context_by_key


def build_player_season_rows_from_player_game_rows(
    player_game_rows: list[dict[str, object]],
    player_birth_date_by_person: dict[int, date] | None = None,
    player_game_possession_context_by_key: dict[tuple[str, int], dict[str, float | None]] | None = None,
    player_game_defensive_shot_context_by_key: dict[tuple[str, int], dict[str, float | None]] | None = None,
    player_game_opportunity_context_by_key: dict[tuple[str, int], dict[str, float | None]] | None = None,
    team_game_context_by_key: dict[tuple[str, int], dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    grouped: dict[tuple[int, str, str], dict[str, object]] = {}

    for row in player_game_rows:
        person_id = to_positive_int_or_none(row.get("person_id"))
        season_year = to_str_or_none(row.get("season_year"))
        season_type = to_str_or_none(row.get("season_type"))
        if person_id is None or season_year is None or season_type is None:
            continue

        key = (person_id, season_year, season_type)
        current = grouped.setdefault(
            key,
            {
                "person_id": person_id,
                "season_year": season_year,
                "season_type": season_type,
                "_team_ids": set(),
                "games_played": 0,
                "games_started": 0,
                "total_minutes": 0.0,
                "points_total": 0,
                "assists_total": 0,
                "rebounds_total": 0,
                "offensive_rebounds_total": 0,
                "defensive_rebounds_total": 0,
                "steals_total": 0,
                "blocks_total": 0,
                "turnovers_total": 0,
                "field_goals_made_total": 0,
                "field_goals_attempted_total": 0,
                "three_pointers_made_total": 0,
                "three_pointers_attempted_total": 0,
                "two_pointers_made_total": 0,
                "two_pointers_attempted_total": 0,
                "free_throws_made_total": 0,
                "free_throws_attempted_total": 0,
                "opponent_blocks_total": 0,
                "offensive_fouls_committed_total": 0,
                "fouls_drawn_total": 0,
                "personal_fouls_committed_total": 0,
                "technical_fouls_committed_total": 0,
                "fast_break_points_total": 0,
                "points_in_paint_total": 0,
                "second_chance_points_total": 0,
                "plus_minus_total": 0,
                "offensive_possessions_total": 0.0,
                "defensive_possessions_total": 0.0,
                "used_offensive_possessions_total": 0.0,
                "team_points_for_while_on_court_total": 0.0,
                "team_points_against_while_on_court_total": 0.0,
                "team_minutes_total_for_usage": 0.0,
                "team_field_goals_attempted_total_for_usage": 0,
                "team_free_throws_attempted_total_for_usage": 0,
                "team_turnovers_total_for_usage": 0,
                "opponent_two_point_attempts_while_on_court_total": 0.0,
                "teammate_field_goals_made_while_on_court_total": 0.0,
                "offensive_rebound_opportunities_while_on_court_total": 0.0,
                "defensive_rebound_opportunities_while_on_court_total": 0.0,
                "rebound_opportunities_while_on_court_total": 0.0,
            },
        )

        team_id = to_positive_int_or_none(row.get("team_id"))
        if team_id is not None:
            current["_team_ids"].add(team_id)
        played_flag = games_played_from_values(row.get("did_play"), row.get("minutes_played"))
        current["games_played"] = (to_int_or_none(current.get("games_played")) or 0) + played_flag
        current["games_started"] = (to_int_or_none(current.get("games_started")) or 0) + (
            1 if to_int_or_none(row.get("is_starter")) == 1 else 0
        )
        current["total_minutes"] = (to_float_or_none(current.get("total_minutes")) or 0.0) + (
            to_float_or_none(row.get("minutes_played")) or 0.0
        )
        current["points_total"] = (to_int_or_none(current.get("points_total")) or 0) + (
            to_int_or_none(row.get("points")) or 0
        )
        current["assists_total"] = (to_int_or_none(current.get("assists_total")) or 0) + (
            to_int_or_none(row.get("assists")) or 0
        )
        current["rebounds_total"] = (to_int_or_none(current.get("rebounds_total")) or 0) + (
            to_int_or_none(row.get("total_rebounds")) or 0
        )
        current["offensive_rebounds_total"] = (to_int_or_none(current.get("offensive_rebounds_total")) or 0) + (
            to_int_or_none(row.get("offensive_rebounds")) or 0
        )
        current["defensive_rebounds_total"] = (to_int_or_none(current.get("defensive_rebounds_total")) or 0) + (
            to_int_or_none(row.get("defensive_rebounds")) or 0
        )
        current["steals_total"] = (to_int_or_none(current.get("steals_total")) or 0) + (
            to_int_or_none(row.get("steals")) or 0
        )
        current["blocks_total"] = (to_int_or_none(current.get("blocks_total")) or 0) + (
            to_int_or_none(row.get("blocks")) or 0
        )
        current["turnovers_total"] = (to_int_or_none(current.get("turnovers_total")) or 0) + (
            to_int_or_none(row.get("turnovers")) or 0
        )
        current["field_goals_made_total"] = (to_int_or_none(current.get("field_goals_made_total")) or 0) + (
            to_int_or_none(row.get("field_goals_made")) or 0
        )
        current["field_goals_attempted_total"] = (
            to_int_or_none(current.get("field_goals_attempted_total")) or 0
        ) + (to_int_or_none(row.get("field_goals_attempted")) or 0)
        current["three_pointers_made_total"] = (
            to_int_or_none(current.get("three_pointers_made_total")) or 0
        ) + (to_int_or_none(row.get("three_pointers_made")) or 0)
        current["three_pointers_attempted_total"] = (
            to_int_or_none(current.get("three_pointers_attempted_total")) or 0
        ) + (to_int_or_none(row.get("three_pointers_attempted")) or 0)
        current["two_pointers_made_total"] = (
            to_int_or_none(current.get("two_pointers_made_total")) or 0
        ) + (to_int_or_none(row.get("two_pointers_made")) or 0)
        current["two_pointers_attempted_total"] = (
            to_int_or_none(current.get("two_pointers_attempted_total")) or 0
        ) + (to_int_or_none(row.get("two_pointers_attempted")) or 0)
        current["free_throws_made_total"] = (to_int_or_none(current.get("free_throws_made_total")) or 0) + (
            to_int_or_none(row.get("free_throws_made")) or 0
        )
        current["free_throws_attempted_total"] = (
            to_int_or_none(current.get("free_throws_attempted_total")) or 0
        ) + (to_int_or_none(row.get("free_throws_attempted")) or 0)
        current["opponent_blocks_total"] = (
            to_int_or_none(current.get("opponent_blocks_total")) or 0
        ) + (to_int_or_none(row.get("opponent_blocks")) or 0)
        current["offensive_fouls_committed_total"] = (
            to_int_or_none(current.get("offensive_fouls_committed_total")) or 0
        ) + (to_int_or_none(row.get("offensive_fouls_committed")) or 0)
        current["fouls_drawn_total"] = (to_int_or_none(current.get("fouls_drawn_total")) or 0) + (
            to_int_or_none(row.get("fouls_drawn")) or 0
        )
        current["personal_fouls_committed_total"] = (
            to_int_or_none(current.get("personal_fouls_committed_total")) or 0
        ) + (to_int_or_none(row.get("personal_fouls_committed")) or 0)
        current["technical_fouls_committed_total"] = (
            to_int_or_none(current.get("technical_fouls_committed_total")) or 0
        ) + (to_int_or_none(row.get("technical_fouls_committed")) or 0)
        current["fast_break_points_total"] = (
            to_int_or_none(current.get("fast_break_points_total")) or 0
        ) + (to_int_or_none(row.get("fast_break_points")) or 0)
        current["points_in_paint_total"] = (
            to_int_or_none(current.get("points_in_paint_total")) or 0
        ) + (to_int_or_none(row.get("points_in_paint")) or 0)
        current["second_chance_points_total"] = (
            to_int_or_none(current.get("second_chance_points_total")) or 0
        ) + (to_int_or_none(row.get("second_chance_points")) or 0)
        current["plus_minus_total"] = (to_int_or_none(current.get("plus_minus_total")) or 0) + (
            to_int_or_none(row.get("plus_minus")) or 0
        )

        player_context_key = (
            to_str_or_none(row.get("game_id")),
            to_positive_int_or_none(row.get("person_id")),
        )
        possession_context = (player_game_possession_context_by_key or {}).get(player_context_key, {})
        shot_context = (player_game_defensive_shot_context_by_key or {}).get(player_context_key, {})
        opportunity_context = (player_game_opportunity_context_by_key or {}).get(player_context_key, {})
        team_game_context = (team_game_context_by_key or {}).get(
            (
                to_str_or_none(row.get("game_id")),
                to_positive_int_or_none(row.get("team_id")),
            ),
            {},
        )
        current["offensive_possessions_total"] = (
            to_float_or_none(current.get("offensive_possessions_total")) or 0.0
        ) + (to_float_or_none(possession_context.get("offensive_possessions")) or 0.0)
        current["defensive_possessions_total"] = (
            to_float_or_none(current.get("defensive_possessions_total")) or 0.0
        ) + (to_float_or_none(possession_context.get("defensive_possessions")) or 0.0)
        current["used_offensive_possessions_total"] = (
            to_float_or_none(current.get("used_offensive_possessions_total")) or 0.0
        ) + (to_float_or_none(possession_context.get("used_offensive_possessions")) or 0.0)
        current["team_points_for_while_on_court_total"] = (
            to_float_or_none(current.get("team_points_for_while_on_court_total")) or 0.0
        ) + (to_float_or_none(possession_context.get("team_points_for_while_on_court")) or 0.0)
        current["team_points_against_while_on_court_total"] = (
            to_float_or_none(current.get("team_points_against_while_on_court_total")) or 0.0
        ) + (to_float_or_none(possession_context.get("team_points_against_while_on_court")) or 0.0)
        current["team_minutes_total_for_usage"] = (
            to_float_or_none(current.get("team_minutes_total_for_usage")) or 0.0
        ) + (to_float_or_none(team_game_context.get("minutes_played")) or 0.0)
        current["team_field_goals_attempted_total_for_usage"] = (
            to_int_or_none(current.get("team_field_goals_attempted_total_for_usage")) or 0
        ) + (to_int_or_none(team_game_context.get("field_goals_attempted")) or 0)
        current["team_free_throws_attempted_total_for_usage"] = (
            to_int_or_none(current.get("team_free_throws_attempted_total_for_usage")) or 0
        ) + (to_int_or_none(team_game_context.get("free_throws_attempted")) or 0)
        current["team_turnovers_total_for_usage"] = (
            to_int_or_none(current.get("team_turnovers_total_for_usage")) or 0
        ) + (to_int_or_none(team_game_context.get("turnovers")) or 0)
        current["opponent_two_point_attempts_while_on_court_total"] = (
            to_float_or_none(current.get("opponent_two_point_attempts_while_on_court_total")) or 0.0
        ) + (to_float_or_none(shot_context.get("opponent_two_point_attempts_while_on_court")) or 0.0)
        current["teammate_field_goals_made_while_on_court_total"] = (
            to_float_or_none(current.get("teammate_field_goals_made_while_on_court_total")) or 0.0
        ) + (to_float_or_none(opportunity_context.get("teammate_field_goals_made_while_on_court")) or 0.0)
        current["offensive_rebound_opportunities_while_on_court_total"] = (
            to_float_or_none(current.get("offensive_rebound_opportunities_while_on_court_total")) or 0.0
        ) + (to_float_or_none(opportunity_context.get("offensive_rebound_opportunities_while_on_court")) or 0.0)
        current["defensive_rebound_opportunities_while_on_court_total"] = (
            to_float_or_none(current.get("defensive_rebound_opportunities_while_on_court_total")) or 0.0
        ) + (to_float_or_none(opportunity_context.get("defensive_rebound_opportunities_while_on_court")) or 0.0)
        current["rebound_opportunities_while_on_court_total"] = (
            to_float_or_none(current.get("rebound_opportunities_while_on_court_total")) or 0.0
        ) + (to_float_or_none(opportunity_context.get("rebound_opportunities_while_on_court")) or 0.0)

    season_rows: list[dict[str, object]] = []
    for key in sorted(grouped):
        aggregate = grouped[key]
        team_count = len(aggregate.pop("_team_ids"))
        games_played = to_int_or_none(aggregate.get("games_played")) or 0
        games_started = to_int_or_none(aggregate.get("games_started")) or 0
        total_minutes = to_float_or_none(aggregate.get("total_minutes")) or 0.0
        points_total = to_int_or_none(aggregate.get("points_total")) or 0
        assists_total = to_int_or_none(aggregate.get("assists_total")) or 0
        rebounds_total = to_int_or_none(aggregate.get("rebounds_total")) or 0
        offensive_rebounds_total = to_int_or_none(aggregate.get("offensive_rebounds_total")) or 0
        defensive_rebounds_total = to_int_or_none(aggregate.get("defensive_rebounds_total")) or 0
        steals_total = to_int_or_none(aggregate.get("steals_total")) or 0
        blocks_total = to_int_or_none(aggregate.get("blocks_total")) or 0
        turnovers_total = to_int_or_none(aggregate.get("turnovers_total")) or 0
        field_goals_made_total = to_int_or_none(aggregate.get("field_goals_made_total")) or 0
        field_goals_attempted_total = to_int_or_none(aggregate.get("field_goals_attempted_total")) or 0
        three_pointers_made_total = to_int_or_none(aggregate.get("three_pointers_made_total")) or 0
        three_pointers_attempted_total = to_int_or_none(aggregate.get("three_pointers_attempted_total")) or 0
        two_pointers_made_total = to_int_or_none(aggregate.get("two_pointers_made_total")) or 0
        two_pointers_attempted_total = to_int_or_none(aggregate.get("two_pointers_attempted_total")) or 0
        free_throws_made_total = to_int_or_none(aggregate.get("free_throws_made_total")) or 0
        free_throws_attempted_total = to_int_or_none(aggregate.get("free_throws_attempted_total")) or 0
        opponent_blocks_total = to_int_or_none(aggregate.get("opponent_blocks_total")) or 0
        offensive_fouls_committed_total = (
            to_int_or_none(aggregate.get("offensive_fouls_committed_total")) or 0
        )
        fouls_drawn_total = to_int_or_none(aggregate.get("fouls_drawn_total")) or 0
        personal_fouls_committed_total = (
            to_int_or_none(aggregate.get("personal_fouls_committed_total")) or 0
        )
        technical_fouls_committed_total = (
            to_int_or_none(aggregate.get("technical_fouls_committed_total")) or 0
        )
        fast_break_points_total = to_int_or_none(aggregate.get("fast_break_points_total")) or 0
        points_in_paint_total = to_int_or_none(aggregate.get("points_in_paint_total")) or 0
        second_chance_points_total = to_int_or_none(aggregate.get("second_chance_points_total")) or 0
        plus_minus_total = to_int_or_none(aggregate.get("plus_minus_total")) or 0
        offensive_possessions_total = to_float_or_none(aggregate.get("offensive_possessions_total")) or 0.0
        defensive_possessions_total = to_float_or_none(aggregate.get("defensive_possessions_total")) or 0.0
        used_offensive_possessions_total = to_float_or_none(aggregate.get("used_offensive_possessions_total")) or 0.0
        team_points_for_while_on_court_total = (
            to_float_or_none(aggregate.get("team_points_for_while_on_court_total")) or 0.0
        )
        team_points_against_while_on_court_total = (
            to_float_or_none(aggregate.get("team_points_against_while_on_court_total")) or 0.0
        )
        team_minutes_total_for_usage = to_float_or_none(aggregate.get("team_minutes_total_for_usage")) or 0.0
        team_field_goals_attempted_total_for_usage = (
            to_int_or_none(aggregate.get("team_field_goals_attempted_total_for_usage")) or 0
        )
        team_free_throws_attempted_total_for_usage = (
            to_int_or_none(aggregate.get("team_free_throws_attempted_total_for_usage")) or 0
        )
        team_turnovers_total_for_usage = to_int_or_none(aggregate.get("team_turnovers_total_for_usage")) or 0
        opponent_two_point_attempts_while_on_court_total = (
            to_float_or_none(aggregate.get("opponent_two_point_attempts_while_on_court_total")) or 0.0
        )
        teammate_field_goals_made_while_on_court_total = (
            to_float_or_none(aggregate.get("teammate_field_goals_made_while_on_court_total")) or 0.0
        )
        offensive_rebound_opportunities_while_on_court_total = (
            to_float_or_none(aggregate.get("offensive_rebound_opportunities_while_on_court_total")) or 0.0
        )
        defensive_rebound_opportunities_while_on_court_total = (
            to_float_or_none(aggregate.get("defensive_rebound_opportunities_while_on_court_total")) or 0.0
        )
        rebound_opportunities_while_on_court_total = (
            to_float_or_none(aggregate.get("rebound_opportunities_while_on_court_total")) or 0.0
        )
        possessions = (offensive_possessions_total + defensive_possessions_total) / 2.0
        proxy_player_usage_numerator = (
            float(field_goals_attempted_total)
            + (0.44 * float(free_throws_attempted_total))
            + float(turnovers_total)
        )
        usage_percentage = _counted_usage_percentage(
            offensive_possessions_total=offensive_possessions_total,
            used_offensive_possessions_total=used_offensive_possessions_total,
            proxy_player_usage_numerator=proxy_player_usage_numerator,
        )
        if usage_percentage is None:
            usage_percentage = _proxy_usage_percentage(
                player_field_goals_attempted_total=field_goals_attempted_total,
                player_free_throws_attempted_total=free_throws_attempted_total,
                player_turnovers_total=turnovers_total,
                player_minutes_total=total_minutes,
                team_field_goals_attempted_total=team_field_goals_attempted_total_for_usage,
                team_free_throws_attempted_total=team_free_throws_attempted_total_for_usage,
                team_turnovers_total=team_turnovers_total_for_usage,
                team_minutes_total=team_minutes_total_for_usage,
            )
        true_shooting_denominator = 2.0 * (
            field_goals_attempted_total + (0.44 * free_throws_attempted_total)
        )
        season_start_year = season_start_year_from_label(aggregate.get("season_year"))
        birth_date = (player_birth_date_by_person or {}).get(aggregate["person_id"])
        season_rows.append(
            {
                **aggregate,
                "age_on_jan_31": (
                    _age_in_completed_years(
                        birth_date=birth_date,
                        reference_date=_season_january_thirty_first(season_start_year),
                    )
                    if season_start_year is not None
                    else None
                ),
                "team_count": team_count,
                "is_multi_team_season": team_count > 1,
                "games_played": games_played,
                "games_started": games_started,
                "minutes_total": round(total_minutes, 1),
                "minutes_per_game": round(total_minutes / games_played, 1) if games_played > 0 else None,
                "points_total": points_total,
                "points_per_game": _rounded_ratio(points_total, games_played),
                "assists_total": assists_total,
                "assists_per_game": _rounded_ratio(assists_total, games_played),
                "rebounds_total": rebounds_total,
                "rebounds_per_game": _rounded_ratio(rebounds_total, games_played),
                "offensive_rebounds_total": offensive_rebounds_total,
                "defensive_rebounds_total": defensive_rebounds_total,
                "offensive_rebounds_per_game": _rounded_ratio(offensive_rebounds_total, games_played),
                "defensive_rebounds_per_game": _rounded_ratio(defensive_rebounds_total, games_played),
                "field_goals_made_total": field_goals_made_total,
                "field_goals_made_per_game": _rounded_ratio(field_goals_made_total, games_played),
                "field_goals_attempted_total": field_goals_attempted_total,
                "field_goals_attempted_per_game": _rounded_ratio(field_goals_attempted_total, games_played),
                "field_goals_percentage": _rounded_ratio(
                    field_goals_made_total,
                    field_goals_attempted_total,
                    scale=100.0,
                ),
                "three_pointers_made_total": three_pointers_made_total,
                "three_pointers_made_per_game": _rounded_ratio(three_pointers_made_total, games_played),
                "three_pointers_attempted_total": three_pointers_attempted_total,
                "three_pointers_attempted_per_game": _rounded_ratio(
                    three_pointers_attempted_total, games_played
                ),
                "three_pointers_percentage": _rounded_ratio(
                    three_pointers_made_total,
                    three_pointers_attempted_total,
                    scale=100.0,
                ),
                "two_pointers_made_total": two_pointers_made_total,
                "two_pointers_made_per_game": _rounded_ratio(two_pointers_made_total, games_played),
                "two_pointers_attempted_total": two_pointers_attempted_total,
                "two_pointers_attempted_per_game": _rounded_ratio(
                    two_pointers_attempted_total, games_played
                ),
                "two_pointers_percentage": _rounded_ratio(
                    two_pointers_made_total,
                    two_pointers_attempted_total,
                    scale=100.0,
                ),
                "free_throws_made_total": free_throws_made_total,
                "free_throws_made_per_game": _rounded_ratio(free_throws_made_total, games_played),
                "free_throws_attempted_total": free_throws_attempted_total,
                "free_throws_attempted_per_game": _rounded_ratio(
                    free_throws_attempted_total, games_played
                ),
                "free_throws_percentage": _rounded_ratio(
                    free_throws_made_total,
                    free_throws_attempted_total,
                    scale=100.0,
                ),
                "opponent_blocks_total": opponent_blocks_total,
                "offensive_fouls_committed_total": offensive_fouls_committed_total,
                "fouls_drawn_total": fouls_drawn_total,
                "personal_fouls_committed_total": personal_fouls_committed_total,
                "personal_fouls_committed_per_game": _rounded_ratio(
                    personal_fouls_committed_total, games_played
                ),
                "technical_fouls_committed_total": technical_fouls_committed_total,
                "fast_break_points_total": fast_break_points_total,
                "points_in_paint_total": points_in_paint_total,
                "second_chance_points_total": second_chance_points_total,
                "steals_total": steals_total,
                "steals_per_game": _rounded_ratio(steals_total, games_played),
                "blocks_total": blocks_total,
                "blocks_per_game": _rounded_ratio(blocks_total, games_played),
                "turnovers_total": turnovers_total,
                "turnovers_per_game": _rounded_ratio(turnovers_total, games_played),
                "plus_minus_total": plus_minus_total,
                "assist_to_turnover_ratio": round(assists_total / turnovers_total, 2)
                if turnovers_total > 0
                else None,
                "assist_percentage": round(
                    100.0 * assists_total / teammate_field_goals_made_while_on_court_total,
                    1,
                )
                if teammate_field_goals_made_while_on_court_total > 0
                else None,
                "offensive_rebound_percentage": round(
                    100.0 * offensive_rebounds_total / offensive_rebound_opportunities_while_on_court_total,
                    1,
                )
                if offensive_rebound_opportunities_while_on_court_total > 0
                else None,
                "defensive_rebound_percentage": round(
                    100.0 * defensive_rebounds_total / defensive_rebound_opportunities_while_on_court_total,
                    1,
                )
                if defensive_rebound_opportunities_while_on_court_total > 0
                else None,
                "rebound_percentage": round(
                    100.0 * rebounds_total / rebound_opportunities_while_on_court_total,
                    1,
                )
                if rebound_opportunities_while_on_court_total > 0
                else None,
                "effective_field_goal_percentage": round(
                    100.0 * (field_goals_made_total + (0.5 * three_pointers_made_total))
                    / field_goals_attempted_total,
                    1,
                )
                if field_goals_attempted_total > 0
                else None,
                "three_point_attempt_rate": round(
                    three_pointers_attempted_total / field_goals_attempted_total,
                    3,
                )
                if field_goals_attempted_total > 0
                else None,
                "free_throw_attempt_rate": round(
                    free_throws_attempted_total / field_goals_attempted_total,
                    3,
                )
                if field_goals_attempted_total > 0
                else None,
                "true_shooting_percentage": round(100.0 * points_total / true_shooting_denominator, 1)
                if true_shooting_denominator > 0
                else None,
                "usage_percentage": usage_percentage,
                "offensive_possessions_total": round(offensive_possessions_total, 1)
                if offensive_possessions_total > 0
                else None,
                "defensive_possessions_total": round(defensive_possessions_total, 1)
                if defensive_possessions_total > 0
                else None,
                "possessions": round(possessions, 1) if possessions > 0 else None,
                "offensive_rating": round(
                    100.0 * team_points_for_while_on_court_total / offensive_possessions_total,
                    1,
                )
                if offensive_possessions_total > 0
                else None,
                "defensive_rating": round(
                    100.0 * team_points_against_while_on_court_total / defensive_possessions_total,
                    1,
                )
                if defensive_possessions_total > 0
                else None,
                "net_rating": round(
                    (100.0 * team_points_for_while_on_court_total / offensive_possessions_total)
                    - (100.0 * team_points_against_while_on_court_total / defensive_possessions_total),
                    1,
                )
                if offensive_possessions_total > 0 and defensive_possessions_total > 0
                else None,
                "pace": round(48.0 * possessions / total_minutes, 1)
                if possessions > 0 and total_minutes > 0
                else None,
                "steal_percentage": round(100.0 * steals_total / defensive_possessions_total, 1)
                if defensive_possessions_total > 0
                else None,
                "block_percentage": round(
                    100.0 * blocks_total / opponent_two_point_attempts_while_on_court_total,
                    1,
                )
                if opponent_two_point_attempts_while_on_court_total > 0
                else None,
            }
        )
    return season_rows


def build_player_season_rows_from_tables(
    player_table: pa.Table,
    box_table: pa.Table,
    schedule_table: pa.Table,
    team_game_table: pa.Table,
    player_bio_table: pa.Table | None = None,
    bridge_table: pa.Table | None = None,
    bbr_profile_table: pa.Table | None = None,
    player_game_possession_context_table: pa.Table | None = None,
    player_game_defensive_shot_context_table: pa.Table | None = None,
    player_game_opportunity_context_table: pa.Table | None = None,
    team_usage_context_table: pa.Table | None = None,
) -> list[dict[str, object]]:
    player_game_rows = build_player_game_rows_from_tables(
        player_table,
        box_table,
        schedule_table,
        team_game_table,
        team_usage_context_table=team_usage_context_table,
    )
    team_game_context_by_key = build_team_usage_context_map_from_table(
        team_usage_context_table if team_usage_context_table is not None else team_game_table
    )
    player_birth_date_by_person = build_player_birth_date_map_from_tables(
        player_bio_table, bridge_table, bbr_profile_table
    )
    player_game_possession_context_by_key = build_player_game_possession_context_map_from_table(
        player_game_possession_context_table
    )
    player_game_defensive_shot_context_by_key = build_player_game_defensive_shot_context_map_from_table(
        player_game_defensive_shot_context_table
    )
    player_game_opportunity_context_by_key = build_player_game_opportunity_context_map_from_table(
        player_game_opportunity_context_table
    )
    return build_player_season_rows_from_player_game_rows(
        player_game_rows,
        player_birth_date_by_person,
        player_game_possession_context_by_key,
        player_game_defensive_shot_context_by_key,
        player_game_opportunity_context_by_key,
        team_game_context_by_key,
    )


def main() -> None:
    s3_client = boto3.client("s3")
    player_table = read_parquet_table_from_s3(
        s3_client, PLAYER_SOURCE_KEY, PLAYER_REQUIRED_COLUMNS
    )
    box_table = read_parquet_table_from_s3(
        s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS
    )
    schedule_table = read_parquet_table_from_s3(
        s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS
    )
    team_game_table = read_parquet_table_from_s3(
        s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS
    )
    team_usage_context_table = read_parquet_table_from_s3(
        s3_client, TEAM_GAME_USAGE_SOURCE_KEY, TEAM_GAME_USAGE_REQUIRED_COLUMNS
    )
    player_bio_table = read_parquet_table_from_s3(
        s3_client, PLAYER_BIO_SOURCE_KEY, PLAYER_BIO_REQUIRED_COLUMNS
    )
    bridge_table = read_parquet_table_from_s3(
        s3_client, BBR_BRIDGE_SOURCE_KEY, BBR_BRIDGE_REQUIRED_COLUMNS
    )
    bbr_profile_table = read_parquet_table_from_s3(
        s3_client, BBR_PROFILE_SOURCE_KEY, BBR_PROFILE_REQUIRED_COLUMNS
    )
    player_game_possession_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        PLAYER_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS,
    )
    player_game_defensive_shot_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS,
    )
    player_game_opportunity_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_GAME_OPPORTUNITY_CONTEXT_SOURCE_KEY,
        PLAYER_GAME_OPPORTUNITY_CONTEXT_REQUIRED_COLUMNS,
    )
    rows = build_player_season_rows_from_tables(
        player_table,
        box_table,
        schedule_table,
        team_game_table,
        player_bio_table,
        bridge_table,
        bbr_profile_table,
        player_game_possession_context_table,
        player_game_defensive_shot_context_table,
        player_game_opportunity_context_table,
        team_usage_context_table,
    )
    write_parquet_to_s3(rows, PLAYER_SEASON_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
