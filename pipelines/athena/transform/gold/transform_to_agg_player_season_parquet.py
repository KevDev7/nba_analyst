"""
Build gold agg_player_season from core gold facts and dimensions.

Reads:
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_player_game/fct_player_game.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/fct_team_game/fct_team_game.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_player/dim_player.parquet
  s3://nba-analytics-lakehouse-dev/legacy_gold/dim_team/dim_team.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/legacy_gold/agg_player_season/agg_player_season.parquet
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError
from dotenv import load_dotenv

try:
    from pipelines.athena.transform.gold.gold_transform_helpers import (
        S3_BUCKET,
        choose_primary_team,
        games_played_from_values,
        normalize_game_id,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        safe_ratio,
        season_type_label_from_code,
        to_bool_or_none,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        choose_primary_team,
        games_played_from_values,
        normalize_game_id,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        safe_ratio,
        season_type_label_from_code,
        to_bool_or_none,
        to_float_or_none,
        to_int_or_none,
        to_str_or_none,
        write_parquet_to_s3,
    )

load_dotenv(override=True)

FACT_SOURCE_KEY = "legacy_gold/fct_player_game/fct_player_game.parquet"
TEAM_FACT_SOURCE_KEY = "legacy_gold/fct_team_game/fct_team_game.parquet"
DIM_PLAYER_SOURCE_KEY = "legacy_gold/dim_player/dim_player.parquet"
DIM_TEAM_SOURCE_KEY = "legacy_gold/dim_team/dim_team.parquet"
PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY = "silver/player_game_possession_context.parquet"
DESTINATION_KEY = "legacy_gold/agg_player_season/agg_player_season.parquet"
SILVER_POSSESSIONS_PREFIX = "silver/possessions/"
SILVER_EVENT_CONTEXT_PREFIX = "silver/pbpstats_event_context_v1/"
SILVER_PLAYBYPLAY_PREFIX = "silver/playbyplay/"

RECORD_SOURCE = (
    "gold.fct_player_game|gold.fct_team_game|gold.dim_player|gold.dim_team|silver.player_game_possession_context"
)

FACT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "team_id",
    "did_play",
    "is_starter",
    "seconds_played_total",
    "points",
    "assists",
    "rebounds_total",
    "rebounds_offensive",
    "rebounds_defensive",
    "steals",
    "blocks",
    "turnovers",
    "raw_plus_value",
    "raw_minus_value",
    "plus_minus_points",
    "field_goals_made",
    "field_goals_attempted",
    "three_pointers_made",
    "three_pointers_attempted",
    "free_throws_made",
    "free_throws_attempted",
    "points_fast_break",
    "points_in_the_paint",
    "points_second_chance",
    "fouls_offensive",
    "fouls_drawn",
    "fouls_personal",
    "fouls_technical",
    "season_year",
    "season_start_year",
    "raw_season_type_code",
    "season_type",
]

TEAM_FACT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "opponent_team_id",
    "score",
    "opponent_score",
    "seconds_played_total",
    "field_goals_attempted",
    "free_throws_attempted",
    "rebounds_offensive",
    "turnovers",
    "is_win",
    "is_loss",
]

DIM_PLAYER_REQUIRED_COLUMNS = [
    "person_id",
    "player_sk",
    "birth_date",
    "is_current",
    "valid_from_utc",
]

DIM_TEAM_REQUIRED_COLUMNS = [
    "team_id",
    "team_sk",
    "team_abbreviation",
    "team_name",
    "is_current",
    "valid_from_utc",
]

PLAYER_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "exact_game_flag",
    "ot_fallback_game_flag",
    "event_estimated_game_flag",
    "boxscore_estimated_game_flag",
    "missing_game_flag",
    "offensive_possessions",
    "defensive_possessions",
    "team_points_for_while_on_court",
    "team_points_against_while_on_court",
]

PLAYER_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "person_id",
    "exact_game_flag",
    "event_estimated_game_flag",
    "boxscore_estimated_game_flag",
    "missing_game_flag",
    "opponent_two_point_attempts_while_on_court",
]

POSSESSIONS_REQUIRED_COLUMNS = [
    "gameId",
    "offenseTeamId",
    "defenseTeamId",
    "offenseHomeAway",
    "defenseHomeAway",
    "pointsScoredOnPossession",
    "countsAsPossession",
    "homeLineupId",
    "awayLineupId",
    "lineupValidFlag",
]

EVENT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "event_num",
    "home_team_id",
    "away_team_id",
    "home_current_player_ids",
    "away_current_player_ids",
    "home_lineup_id",
    "away_lineup_id",
]

PLAYBYPLAY_REQUIRED_COLUMNS = [
    "gameId",
    "actionNumber",
    "orderNumber",
    "scoreHome",
    "scoreAway",
    "resolvedOffenseTeamId",
    "resolvedDefenseTeamId",
    "countAsPossession",
]

POSSESSION_TOTAL_FIELDS = [
    "offensive_possessions_total",
    "defensive_possessions_total",
    "team_points_for_while_on_court_total",
    "team_points_against_while_on_court_total",
]

POSSESSION_COUNTER_FIELDS = [
    "on_court_games_covered_total",
    "ot_fallback_games_played",
    "event_estimated_games_played",
    "boxscore_estimated_games_played",
    "missing_possession_games_played",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("agg_player_season_sk", pa.int64()),
        pa.field("person_id", pa.int64()),
        pa.field("current_player_sk", pa.int64()),
        pa.field("season_year", pa.string()),
        pa.field("season_start_year", pa.int64()),
        pa.field("raw_season_type_code", pa.string()),
        pa.field("season_type", pa.string()),
        pa.field("age_on_jan_31", pa.int64()),
        pa.field("primary_team_id", pa.int64()),
        pa.field("primary_team_abbreviation", pa.string()),
        pa.field("primary_team_name", pa.string()),
        pa.field("is_multi_team_season", pa.int64()),
        pa.field("games_on_roster", pa.int64()),
        pa.field("games_played", pa.int64()),
        pa.field("games_started", pa.int64()),
        pa.field("wins", pa.int64()),
        pa.field("losses", pa.int64()),
        pa.field("team_count", pa.int64()),
        pa.field("seconds_played_total", pa.float64()),
        pa.field("seconds_played_average", pa.float64()),
        pa.field("minutes_per_game", pa.float64()),
        pa.field("points_total", pa.int64()),
        pa.field("assists_total", pa.int64()),
        pa.field("rebounds_total", pa.int64()),
        pa.field("steals_total", pa.int64()),
        pa.field("blocks_total", pa.int64()),
        pa.field("turnovers_total", pa.int64()),
        pa.field("double_doubles", pa.int64()),
        pa.field("triple_doubles", pa.int64()),
        pa.field("quadruple_doubles", pa.int64()),
        pa.field("field_goals_percentage", pa.float64()),
        pa.field("three_pointers_percentage", pa.float64()),
        pa.field("free_throws_percentage", pa.float64()),
        pa.field("points_per_game", pa.float64()),
        pa.field("assists_per_game", pa.float64()),
        pa.field("rebounds_per_game", pa.float64()),
        pa.field("rebounds_offensive_total", pa.int64()),
        pa.field("rebounds_defensive_total", pa.int64()),
        pa.field("field_goals_made_total", pa.int64()),
        pa.field("field_goals_attempted_total", pa.int64()),
        pa.field("three_pointers_made_total", pa.int64()),
        pa.field("three_pointers_attempted_total", pa.int64()),
        pa.field("free_throws_made_total", pa.int64()),
        pa.field("free_throws_attempted_total", pa.int64()),
        pa.field("points_fast_break_total", pa.int64()),
        pa.field("points_in_the_paint_total", pa.int64()),
        pa.field("points_second_chance_total", pa.int64()),
        pa.field("fouls_offensive_total", pa.int64()),
        pa.field("fouls_drawn_total", pa.int64()),
        pa.field("fouls_personal_total", pa.int64()),
        pa.field("fouls_technical_total", pa.int64()),
        pa.field("raw_plus_value_total", pa.int64()),
        pa.field("raw_minus_value_total", pa.int64()),
        pa.field("plus_minus_points_total", pa.int64()),
        pa.field("possessions_total", pa.float64()),
        pa.field("record_source", pa.string()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)

SUM_FIELDS: list[tuple[str, str]] = [
    ("points", "points_total"),
    ("assists", "assists_total"),
    ("rebounds_total", "rebounds_total"),
    ("steals", "steals_total"),
    ("blocks", "blocks_total"),
    ("turnovers", "turnovers_total"),
    ("rebounds_offensive", "rebounds_offensive_total"),
    ("rebounds_defensive", "rebounds_defensive_total"),
    ("field_goals_made", "field_goals_made_total"),
    ("field_goals_attempted", "field_goals_attempted_total"),
    ("three_pointers_made", "three_pointers_made_total"),
    ("three_pointers_attempted", "three_pointers_attempted_total"),
    ("free_throws_made", "free_throws_made_total"),
    ("free_throws_attempted", "free_throws_attempted_total"),
    ("points_fast_break", "points_fast_break_total"),
    ("points_in_the_paint", "points_in_the_paint_total"),
    ("points_second_chance", "points_second_chance_total"),
    ("fouls_offensive", "fouls_offensive_total"),
    ("fouls_drawn", "fouls_drawn_total"),
    ("fouls_personal", "fouls_personal_total"),
    ("fouls_technical", "fouls_technical_total"),
    ("raw_plus_value", "raw_plus_value_total"),
    ("raw_minus_value", "raw_minus_value_total"),
    ("plus_minus_points", "plus_minus_points_total"),
]


def _normalize_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _age_in_completed_years(*, birth_date: date | None, reference_date: date) -> int | None:
    if birth_date is None or birth_date > reference_date:
        return None
    years = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


def _season_january_thirty_first(season_start_year: int) -> date:
    return date(season_start_year + 1, 1, 31)


def _normalize_player_ids(value: object) -> list[int] | None:
    if value is None:
        return None
    if hasattr(value, "tolist"):
        value = value.tolist()
    elif isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        return None
    player_ids = [to_int_or_none(item) for item in value]
    if any(player_id is None for player_id in player_ids):
        return None
    normalized = [int(player_id) for player_id in player_ids if player_id is not None]
    if len(normalized) != 5 or len(set(normalized)) != 5:
        return None
    return normalized


def _players_from_lineup_id(lineup_id: object) -> list[int] | None:
    text = to_str_or_none(lineup_id)
    if text is None:
        return None
    parts = text.split("-")
    player_ids = [to_int_or_none(part) for part in parts]
    if any(player_id is None for player_id in player_ids):
        return None
    normalized = [int(player_id) for player_id in player_ids if player_id is not None]
    if len(normalized) != 5 or len(set(normalized)) != 5:
        return None
    return normalized


def _read_parquet_rows_from_s3(
    s3_client,
    key: str,
    columns: list[str],
) -> list[dict[str, Any]] | None:
    try:
        payload = s3_client.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
            return None
        raise
    table = pq.read_table(io.BytesIO(payload), columns=columns)
    return table.to_pylist()


def _init_player_game_possession_stats(person_ids: set[int]) -> dict[int, dict[str, float | int]]:
    return {
        person_id: {
            "offensive_possessions_total": 0.0,
            "defensive_possessions_total": 0.0,
            "team_points_for_while_on_court_total": 0.0,
            "team_points_against_while_on_court_total": 0.0,
            "on_court_games_covered_total": 0,
            "event_estimated_games_played": 0,
            "boxscore_estimated_games_played": 0,
            "missing_possession_games_played": 0,
        }
        for person_id in sorted(person_ids)
    }


def _build_lineup_maps_from_event_context_rows(
    event_context_rows: list[dict[str, Any]] | None,
) -> tuple[int | None, int | None, dict[str, list[int]], dict[str, list[int]]]:
    home_team_id = None
    away_team_id = None
    home_lineups: dict[str, list[int]] = {}
    away_lineups: dict[str, list[int]] = {}
    for row in event_context_rows or []:
        if home_team_id is None:
            home_team_id = to_int_or_none(row.get("home_team_id"))
        if away_team_id is None:
            away_team_id = to_int_or_none(row.get("away_team_id"))
        home_lineup_id = to_str_or_none(row.get("home_lineup_id"))
        away_lineup_id = to_str_or_none(row.get("away_lineup_id"))
        home_players = _normalize_player_ids(row.get("home_current_player_ids"))
        away_players = _normalize_player_ids(row.get("away_current_player_ids"))
        if home_lineup_id is not None and home_players is not None:
            home_lineups.setdefault(home_lineup_id, home_players)
        if away_lineup_id is not None and away_players is not None:
            away_lineups.setdefault(away_lineup_id, away_players)
    return home_team_id, away_team_id, home_lineups, away_lineups


def _build_event_context_by_event_num(
    event_context_rows: list[dict[str, Any]] | None,
) -> tuple[int | None, int | None, dict[int, tuple[list[int], list[int]]]]:
    home_team_id = None
    away_team_id = None
    context_by_event_num: dict[int, tuple[list[int], list[int]]] = {}
    for row in event_context_rows or []:
        if home_team_id is None:
            home_team_id = to_int_or_none(row.get("home_team_id"))
        if away_team_id is None:
            away_team_id = to_int_or_none(row.get("away_team_id"))
        event_num = to_int_or_none(row.get("event_num"))
        home_players = _normalize_player_ids(row.get("home_current_player_ids"))
        away_players = _normalize_player_ids(row.get("away_current_player_ids"))
        if event_num is None or home_players is None or away_players is None:
            continue
        context_by_event_num[event_num] = (home_players, away_players)
    return home_team_id, away_team_id, context_by_event_num


def build_exact_player_game_possession_stats(
    possession_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
    played_players: dict[int, dict[str, Any]],
) -> dict[int, dict[str, float | int]] | None:
    counted_rows = [
        row
        for row in possession_rows or []
        if to_bool_or_none(row.get("countsAsPossession")) is True
    ]
    if not counted_rows:
        return None

    stats = _init_player_game_possession_stats(set(played_players))
    home_team_id, away_team_id, home_lineups, away_lineups = _build_lineup_maps_from_event_context_rows(
        event_context_rows
    )

    for row in counted_rows:
        offense_team_id = to_int_or_none(row.get("offenseTeamId"))
        defense_team_id = to_int_or_none(row.get("defenseTeamId"))
        offense_home_away = to_str_or_none(row.get("offenseHomeAway"))
        defense_home_away = to_str_or_none(row.get("defenseHomeAway"))
        if offense_team_id is None or defense_team_id is None:
            return None

        home_lineup_id = to_str_or_none(row.get("homeLineupId"))
        away_lineup_id = to_str_or_none(row.get("awayLineupId"))
        offense_lineup_id = home_lineup_id if offense_home_away == "h" else away_lineup_id if offense_home_away == "v" else None
        defense_lineup_id = home_lineup_id if defense_home_away == "h" else away_lineup_id if defense_home_away == "v" else None

        if offense_lineup_id is None and home_team_id is not None and away_team_id is not None:
            offense_lineup_id = home_lineup_id if offense_team_id == home_team_id else away_lineup_id
        if defense_lineup_id is None and home_team_id is not None and away_team_id is not None:
            defense_lineup_id = home_lineup_id if defense_team_id == home_team_id else away_lineup_id

        offense_players = (
            home_lineups.get(offense_lineup_id) if offense_lineup_id is not None and offense_lineup_id in home_lineups else None
        )
        if offense_players is None and offense_lineup_id is not None:
            offense_players = away_lineups.get(offense_lineup_id)
        if offense_players is None:
            offense_players = _players_from_lineup_id(offense_lineup_id)

        defense_players = (
            home_lineups.get(defense_lineup_id) if defense_lineup_id is not None and defense_lineup_id in home_lineups else None
        )
        if defense_players is None and defense_lineup_id is not None:
            defense_players = away_lineups.get(defense_lineup_id)
        if defense_players is None:
            defense_players = _players_from_lineup_id(defense_lineup_id)

        if offense_players is None or defense_players is None:
            return None

        points = float(to_int_or_none(row.get("pointsScoredOnPossession")) or 0)
        for person_id in offense_players:
            player_stats = stats.get(person_id)
            if player_stats is None:
                continue
            player_stats["offensive_possessions_total"] += 1.0
            player_stats["team_points_for_while_on_court_total"] += points
        for person_id in defense_players:
            player_stats = stats.get(person_id)
            if player_stats is None:
                continue
            player_stats["defensive_possessions_total"] += 1.0
            player_stats["team_points_against_while_on_court_total"] += points

    for player_stats in stats.values():
        player_stats["on_court_games_covered_total"] = 1
    return stats


def build_event_estimated_player_game_possession_stats(
    playbyplay_rows: list[dict[str, Any]] | None,
    event_context_rows: list[dict[str, Any]] | None,
    played_players: dict[int, dict[str, Any]],
) -> dict[int, dict[str, float | int]] | None:
    if not playbyplay_rows or not event_context_rows:
        return None

    counted_rows = [
        row
        for row in playbyplay_rows
        if to_bool_or_none(row.get("countAsPossession")) is True
    ]
    if not counted_rows:
        return None

    stats = _init_player_game_possession_stats(set(played_players))
    home_team_id, away_team_id, context_by_event_num = _build_event_context_by_event_num(event_context_rows)
    if home_team_id is None or away_team_id is None or not context_by_event_num:
        return None

    previous_score_home = 0
    previous_score_away = 0
    for row in sorted(
        playbyplay_rows,
        key=lambda item: (
            to_int_or_none(item.get("orderNumber")) or 0,
            to_int_or_none(item.get("actionNumber")) or 0,
        ),
    ):
        action_number = to_int_or_none(row.get("actionNumber"))
        context = context_by_event_num.get(action_number or -1)
        score_home = to_int_or_none(row.get("scoreHome")) or previous_score_home
        score_away = to_int_or_none(row.get("scoreAway")) or previous_score_away
        delta_home = max(score_home - previous_score_home, 0)
        delta_away = max(score_away - previous_score_away, 0)
        previous_score_home = score_home
        previous_score_away = score_away

        if delta_home > 0 or delta_away > 0:
            if context is None:
                return None
            home_players, away_players = context
            for person_id in home_players:
                player_stats = stats.get(person_id)
                if player_stats is None:
                    continue
                player_stats["team_points_for_while_on_court_total"] += float(delta_home)
                player_stats["team_points_against_while_on_court_total"] += float(delta_away)
            for person_id in away_players:
                player_stats = stats.get(person_id)
                if player_stats is None:
                    continue
                player_stats["team_points_for_while_on_court_total"] += float(delta_away)
                player_stats["team_points_against_while_on_court_total"] += float(delta_home)

        if to_bool_or_none(row.get("countAsPossession")) is not True:
            continue

        if context is None:
            return None
        home_players, away_players = context
        offense_team_id = to_int_or_none(row.get("resolvedOffenseTeamId"))
        defense_team_id = to_int_or_none(row.get("resolvedDefenseTeamId"))
        if offense_team_id == home_team_id and defense_team_id == away_team_id:
            offense_players = home_players
            defense_players = away_players
        elif offense_team_id == away_team_id and defense_team_id == home_team_id:
            offense_players = away_players
            defense_players = home_players
        else:
            return None

        for person_id in offense_players:
            player_stats = stats.get(person_id)
            if player_stats is None:
                continue
            player_stats["offensive_possessions_total"] += 1.0
        for person_id in defense_players:
            player_stats = stats.get(person_id)
            if player_stats is None:
                continue
            player_stats["defensive_possessions_total"] += 1.0

    for player_stats in stats.values():
        player_stats["event_estimated_games_played"] = 1
    return stats


def build_boxscore_estimated_player_game_possession_stats(
    played_players: dict[int, dict[str, Any]],
    team_game_context_map: dict[tuple[str, int], dict[str, Any]],
    *,
    game_id: str,
) -> dict[int, dict[str, float | int]] | None:
    if not played_players:
        return None

    stats = _init_player_game_possession_stats(set(played_players))
    for person_id, player_info in played_players.items():
        team_id = to_int_or_none(player_info.get("team_id"))
        if team_id is None:
            return None
        team_row = team_game_context_map.get((game_id, team_id))
        if team_row is None:
            return None
        opponent_team_id = to_int_or_none(team_row.get("opponent_team_id"))
        if opponent_team_id is None:
            return None
        opponent_row = team_game_context_map.get((game_id, opponent_team_id))
        if opponent_row is None:
            return None

        team_seconds_played_total = to_float_or_none(team_row.get("seconds_played_total"))
        player_seconds_played_total = to_float_or_none(player_info.get("seconds_played_total")) or 0.0
        if team_seconds_played_total is None or team_seconds_played_total <= 0:
            return None

        team_possessions_estimate = 0.5 * (
            (
                float(to_int_or_none(team_row.get("field_goals_attempted")) or 0)
                + (0.44 * float(to_int_or_none(team_row.get("free_throws_attempted")) or 0))
                - float(to_int_or_none(team_row.get("rebounds_offensive")) or 0)
                + float(to_int_or_none(team_row.get("turnovers")) or 0)
            )
            + (
                float(to_int_or_none(opponent_row.get("field_goals_attempted")) or 0)
                + (0.44 * float(to_int_or_none(opponent_row.get("free_throws_attempted")) or 0))
                - float(to_int_or_none(opponent_row.get("rebounds_offensive")) or 0)
                + float(to_int_or_none(opponent_row.get("turnovers")) or 0)
            )
        )
        minute_share = player_seconds_played_total / (team_seconds_played_total / 5.0)
        player_stats = stats[person_id]
        player_stats["offensive_possessions_total"] = minute_share * team_possessions_estimate
        player_stats["defensive_possessions_total"] = minute_share * team_possessions_estimate
        player_stats["team_points_for_while_on_court_total"] = minute_share * float(
            to_int_or_none(team_row.get("score")) or 0
        )
        player_stats["team_points_against_while_on_court_total"] = minute_share * float(
            to_int_or_none(team_row.get("opponent_score")) or 0
        )
        player_stats["boxscore_estimated_games_played"] = 1
    return stats


def build_team_game_context_map(team_fact_table: pa.Table) -> dict[tuple[str, int], dict[str, Any]]:
    context_map: dict[tuple[str, int], dict[str, Any]] = {}
    for row in team_fact_table.to_pylist():
        game_id = normalize_game_id(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        context_map[(game_id, team_id)] = {
            "opponent_team_id": to_int_or_none(row.get("opponent_team_id")),
            "score": to_int_or_none(row.get("score")),
            "opponent_score": to_int_or_none(row.get("opponent_score")),
            "seconds_played_total": to_float_or_none(row.get("seconds_played_total")),
            "field_goals_attempted": to_int_or_none(row.get("field_goals_attempted")),
            "free_throws_attempted": to_int_or_none(row.get("free_throws_attempted")),
            "rebounds_offensive": to_int_or_none(row.get("rebounds_offensive")),
            "turnovers": to_int_or_none(row.get("turnovers")),
        }
    return context_map


def build_player_game_possession_map(
    fact_table: pa.Table,
    team_fact_table: pa.Table,
    s3_client,
) -> dict[tuple[str, int], dict[str, float | int]]:
    played_players_by_game: dict[str, dict[int, dict[str, Any]]] = {}
    for row in fact_table.to_pylist():
        game_id = normalize_game_id(row.get("game_id"))
        person_id = to_int_or_none(row.get("person_id"))
        team_id = to_int_or_none(row.get("team_id"))
        played_flag = games_played_from_values(row.get("did_play"), row.get("seconds_played_total"))
        if game_id is None or person_id is None or team_id is None or played_flag != 1:
            continue
        played_players_by_game.setdefault(game_id, {})[person_id] = {
            "person_id": person_id,
            "team_id": team_id,
            "seconds_played_total": to_float_or_none(row.get("seconds_played_total")) or 0.0,
        }

    team_game_context_map = build_team_game_context_map(team_fact_table)
    player_game_possession_map: dict[tuple[str, int], dict[str, float | int]] = {}

    def _build_game_stats(game_id: str, played_players: dict[int, dict[str, Any]]) -> dict[int, dict[str, float | int]]:
        exact_rows = _read_parquet_rows_from_s3(
            s3_client,
            f"{SILVER_POSSESSIONS_PREFIX}game_id={game_id}.parquet",
            POSSESSIONS_REQUIRED_COLUMNS,
        )
        game_stats = build_exact_player_game_possession_stats(exact_rows, None, played_players)
        event_context_rows = None

        if game_stats is None and exact_rows:
            event_context_rows = _read_parquet_rows_from_s3(
                s3_client,
                f"{SILVER_EVENT_CONTEXT_PREFIX}game_id={game_id}.parquet",
                EVENT_CONTEXT_REQUIRED_COLUMNS,
            )
            game_stats = build_exact_player_game_possession_stats(exact_rows, event_context_rows, played_players)

        if game_stats is None:
            if event_context_rows is None:
                event_context_rows = _read_parquet_rows_from_s3(
                    s3_client,
                    f"{SILVER_EVENT_CONTEXT_PREFIX}game_id={game_id}.parquet",
                    EVENT_CONTEXT_REQUIRED_COLUMNS,
                )
            playbyplay_rows = _read_parquet_rows_from_s3(
                s3_client,
                f"{SILVER_PLAYBYPLAY_PREFIX}game_id={game_id}.parquet",
                PLAYBYPLAY_REQUIRED_COLUMNS,
            )
            game_stats = build_event_estimated_player_game_possession_stats(
                playbyplay_rows,
                event_context_rows,
                played_players,
            )

        if game_stats is None:
            game_stats = build_boxscore_estimated_player_game_possession_stats(
                played_players,
                team_game_context_map,
                game_id=game_id,
            )

        if game_stats is None:
            game_stats = _init_player_game_possession_stats(set(played_players))
            for player_stats in game_stats.values():
                player_stats["missing_possession_games_played"] = 1

        return game_stats

    max_workers = min(16, max(1, len(played_players_by_game)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_build_game_stats, game_id, played_players): game_id
            for game_id, played_players in sorted(played_players_by_game.items())
        }
        for future in as_completed(future_map):
            game_id = future_map[future]
            game_stats = future.result()
            for person_id, player_stats in game_stats.items():
                player_game_possession_map[(game_id, person_id)] = player_stats

    return player_game_possession_map


def build_player_game_possession_map_from_table(
    player_game_possession_context_table: pa.Table,
) -> dict[tuple[str, int], dict[str, float | int]]:
    player_game_possession_map: dict[tuple[str, int], dict[str, float | int]] = {}
    for row in player_game_possession_context_table.to_pylist():
        game_id = normalize_game_id(row.get("game_id"))
        person_id = to_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None:
            continue
        player_game_possession_map[(game_id, person_id)] = {
            "on_court_games_covered_total": to_int_or_none(row.get("exact_game_flag")) or 0,
            "ot_fallback_games_played": to_int_or_none(row.get("ot_fallback_game_flag")) or 0,
            "event_estimated_games_played": to_int_or_none(row.get("event_estimated_game_flag")) or 0,
            "boxscore_estimated_games_played": to_int_or_none(row.get("boxscore_estimated_game_flag")) or 0,
            "missing_possession_games_played": to_int_or_none(row.get("missing_game_flag")) or 0,
            "offensive_possessions_total": to_float_or_none(row.get("offensive_possessions")) or 0.0,
            "defensive_possessions_total": to_float_or_none(row.get("defensive_possessions")) or 0.0,
            "team_points_for_while_on_court_total": to_float_or_none(row.get("team_points_for_while_on_court")) or 0.0,
            "team_points_against_while_on_court_total": to_float_or_none(row.get("team_points_against_while_on_court")) or 0.0,
        }
    return player_game_possession_map


def build_player_game_defensive_shot_context_map_from_table(
    player_game_defensive_shot_context_table: pa.Table,
) -> dict[tuple[str, int], dict[str, float | int]]:
    shot_context_map: dict[tuple[str, int], dict[str, float | int]] = {}
    for row in player_game_defensive_shot_context_table.to_pylist():
        game_id = normalize_game_id(row.get("game_id"))
        person_id = to_int_or_none(row.get("person_id"))
        if game_id is None or person_id is None:
            continue
        shot_context_map[(game_id, person_id)] = {
            "exact_shot_context_games": to_int_or_none(row.get("exact_game_flag")) or 0,
            "event_estimated_shot_context_games": to_int_or_none(row.get("event_estimated_game_flag")) or 0,
            "boxscore_estimated_shot_context_games": to_int_or_none(row.get("boxscore_estimated_game_flag")) or 0,
            "missing_shot_context_games": to_int_or_none(row.get("missing_game_flag")) or 0,
            "opponent_two_point_attempts_while_on_court_total": to_float_or_none(
                row.get("opponent_two_point_attempts_while_on_court")
            )
            or 0.0,
        }
    return shot_context_map


def build_current_player_attrs_map(dim_player_table: pa.Table) -> dict[int, dict[str, object]]:
    latest_rows: dict[int, tuple[dict[str, object], datetime | None]] = {}

    for row in dim_player_table.to_pylist():
        person_id = to_int_or_none(row.get("person_id"))
        player_sk = to_int_or_none(row.get("player_sk"))
        if person_id is None or player_sk is None or to_int_or_none(row.get("is_current")) != 1:
            continue

        valid_from = parse_timestamp_utc(row.get("valid_from_utc"))
        attrs = {
            "current_player_sk": player_sk,
            "birth_date": _normalize_date(row.get("birth_date")),
        }
        current = latest_rows.get(person_id)
        if current is None or (current[1] or datetime.min.replace(tzinfo=timezone.utc)) < (
            valid_from or datetime.min.replace(tzinfo=timezone.utc)
        ):
            latest_rows[person_id] = (attrs, valid_from)

    return {person_id: attrs for person_id, (attrs, _) in latest_rows.items()}


def build_current_team_attrs_map(dim_team_table: pa.Table) -> dict[int, dict[str, str | None]]:
    latest_rows: dict[int, tuple[dict[str, str | None], datetime | None, int | None]] = {}

    for row in dim_team_table.to_pylist():
        team_id = to_int_or_none(row.get("team_id"))
        if team_id is None or to_int_or_none(row.get("is_current")) != 1:
            continue

        attrs = {
            "team_abbreviation": to_str_or_none(row.get("team_abbreviation")),
            "team_name": to_str_or_none(row.get("team_name")),
        }
        valid_from = parse_timestamp_utc(row.get("valid_from_utc"))
        team_sk = to_int_or_none(row.get("team_sk"))
        current = latest_rows.get(team_id)
        current_key = (
            current[1] or datetime.min.replace(tzinfo=timezone.utc),
            current[2] or 0,
        ) if current is not None else None
        candidate_key = (valid_from or datetime.min.replace(tzinfo=timezone.utc), team_sk or 0)
        if current_key is None or candidate_key > current_key:
            latest_rows[team_id] = (attrs, valid_from, team_sk)

    return {team_id: attrs for team_id, (attrs, _, _) in latest_rows.items()}


def build_team_game_result_map(team_fact_table: pa.Table) -> dict[tuple[str, int], dict[str, int]]:
    result_map: dict[tuple[str, int], dict[str, int]] = {}
    for row in team_fact_table.to_pylist():
        game_id = normalize_game_id(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        candidate = {
            "is_win": 1 if to_int_or_none(row.get("is_win")) == 1 else 0,
            "is_loss": 1 if to_int_or_none(row.get("is_loss")) == 1 else 0,
        }
        current = result_map.get((game_id, team_id))
        if current is None or sum(candidate.values()) > sum(current.values()):
            result_map[(game_id, team_id)] = candidate
    return result_map


def _init_agg(
    *,
    person_id: int,
    season_year: str,
    season_start_year: int,
    raw_season_type_code: str,
    season_type: str,
) -> dict[str, Any]:
    agg = {
        "person_id": person_id,
        "season_year": season_year,
        "season_start_year": season_start_year,
        "raw_season_type_code": raw_season_type_code,
        "season_type": season_type,
        "games_on_roster": 0,
        "games_played": 0,
        "games_started": 0,
        "wins": 0,
        "losses": 0,
        "team_count": 0,
        "seconds_played_total": 0.0,
        "current_player_sk": None,
        "primary_team_id": None,
        "primary_team_abbreviation": None,
        "primary_team_name": None,
        "is_multi_team_season": 0,
        "_game_ids": set(),
        "_team_ids": set(),
        "_team_rollups": {},
    }
    for _, agg_field in SUM_FIELDS:
        agg[agg_field] = 0
    for agg_field in POSSESSION_COUNTER_FIELDS:
        agg[agg_field] = 0
    for agg_field in POSSESSION_TOTAL_FIELDS:
        agg[agg_field] = 0.0
    agg["double_doubles"] = 0
    agg["triple_doubles"] = 0
    agg["quadruple_doubles"] = 0
    return agg


def _double_digit_boxscore_category_count(row: dict[str, Any]) -> int:
    categories = (
        to_int_or_none(row.get("points")) or 0,
        to_int_or_none(row.get("rebounds_total")) or 0,
        to_int_or_none(row.get("assists")) or 0,
        to_int_or_none(row.get("steals")) or 0,
        to_int_or_none(row.get("blocks")) or 0,
    )
    return sum(1 for value in categories if value >= 10)


def build_agg_rows(
    fact_table: pa.Table,
    team_game_result_map: dict[tuple[str, int], dict[str, int]],
    current_player_attrs_map: dict[int, dict[str, object]],
    current_team_attrs_map: dict[int, dict[str, str | None]],
    player_game_possession_map: dict[tuple[str, int], dict[str, float | int]] | None = None,
) -> list[dict[str, Any]]:
    aggregations: dict[tuple[int, str, int, str], dict[str, Any]] = {}

    for row in fact_table.to_pylist():
        person_id = to_int_or_none(row.get("person_id"))
        season_year = to_str_or_none(row.get("season_year"))
        season_start_year = to_int_or_none(row.get("season_start_year"))
        raw_season_type_code = to_str_or_none(row.get("raw_season_type_code"))
        if person_id is None or season_year is None or season_start_year is None or raw_season_type_code is None:
            continue

        game_id = normalize_game_id(row.get("game_id"))
        if game_id is None:
            continue

        season_type = to_str_or_none(row.get("season_type")) or season_type_label_from_code(raw_season_type_code) or "unknown"
        key = (person_id, season_year, season_start_year, raw_season_type_code)
        agg = aggregations.get(key)
        if agg is None:
            agg = _init_agg(
                person_id=person_id,
                season_year=season_year,
                season_start_year=season_start_year,
                raw_season_type_code=raw_season_type_code,
                season_type=season_type,
            )
            aggregations[key] = agg

        played_flag = games_played_from_values(row.get("did_play"), row.get("seconds_played_total"))
        starter = 1 if to_int_or_none(row.get("is_starter")) == 1 else 0
        team_id = to_int_or_none(row.get("team_id"))

        if game_id not in agg["_game_ids"]:
            agg["_game_ids"].add(game_id)
            agg["games_on_roster"] += 1
        agg["games_played"] += played_flag
        agg["games_started"] += starter
        agg["seconds_played_total"] += to_float_or_none(row.get("seconds_played_total")) or 0.0

        for source_field, agg_field in SUM_FIELDS:
            agg[agg_field] += to_int_or_none(row.get(source_field)) or 0

        if team_id is not None:
            if team_id not in agg["_team_ids"]:
                agg["_team_ids"].add(team_id)
                agg["team_count"] += 1

            team_rollups = agg["_team_rollups"]
            team_state = team_rollups.setdefault(
                team_id,
                {
                    "team_id": team_id,
                    "games_played": 0,
                    "games_on_roster": 0,
                    "_game_ids": set(),
                },
            )
            if game_id not in team_state["_game_ids"]:
                team_state["_game_ids"].add(game_id)
                team_state["games_on_roster"] += 1
            team_state["games_played"] += played_flag

        if played_flag == 1:
            result = team_game_result_map.get((game_id, team_id), {})
            agg["wins"] += to_int_or_none(result.get("is_win")) or 0
            agg["losses"] += to_int_or_none(result.get("is_loss")) or 0

            double_digit_categories = _double_digit_boxscore_category_count(row)
            if double_digit_categories >= 2:
                agg["double_doubles"] += 1
            if double_digit_categories >= 3:
                agg["triple_doubles"] += 1
            if double_digit_categories >= 4:
                agg["quadruple_doubles"] += 1

            possession_stats = (player_game_possession_map or {}).get((game_id, person_id))
            if possession_stats is not None:
                for agg_field in POSSESSION_COUNTER_FIELDS:
                    agg[agg_field] += to_int_or_none(possession_stats.get(agg_field)) or 0
                for agg_field in POSSESSION_TOTAL_FIELDS:
                    agg[agg_field] += to_float_or_none(possession_stats.get(agg_field)) or 0.0

    rows: list[dict[str, Any]] = []
    for agg in aggregations.values():
        primary_team = choose_primary_team(agg["_team_rollups"].values())
        primary_team_id = primary_team.get("team_id") if primary_team is not None else None
        primary_team_attrs = current_team_attrs_map.get(primary_team_id, {}) if primary_team_id is not None else {}
        player_attrs = current_player_attrs_map.get(agg["person_id"], {})
        player_birth_date = _normalize_date(player_attrs.get("birth_date"))
        seconds_played_average = safe_ratio(agg["seconds_played_total"], agg["games_played"])
        minutes_per_game = round(seconds_played_average / 60.0, 1) if seconds_played_average is not None else None

        row = {
            "person_id": agg["person_id"],
            "current_player_sk": to_int_or_none(player_attrs.get("current_player_sk")),
            "season_year": agg["season_year"],
            "season_start_year": agg["season_start_year"],
            "raw_season_type_code": agg["raw_season_type_code"],
            "season_type": agg["season_type"],
            "age_on_jan_31": _age_in_completed_years(
                birth_date=player_birth_date,
                reference_date=_season_january_thirty_first(agg["season_start_year"]),
            ),
            "primary_team_id": primary_team_id,
            "primary_team_abbreviation": primary_team_attrs.get("team_abbreviation"),
            "primary_team_name": primary_team_attrs.get("team_name"),
            "is_multi_team_season": 1 if agg["team_count"] > 1 else 0,
            "games_on_roster": agg["games_on_roster"],
            "games_played": agg["games_played"],
            "games_started": agg["games_started"],
            "wins": agg["wins"],
            "losses": agg["losses"],
            "team_count": agg["team_count"],
            "seconds_played_total": agg["seconds_played_total"],
            "seconds_played_average": seconds_played_average,
            "minutes_per_game": minutes_per_game,
            "points_total": agg["points_total"],
            "assists_total": agg["assists_total"],
            "rebounds_total": agg["rebounds_total"],
            "steals_total": agg["steals_total"],
            "blocks_total": agg["blocks_total"],
            "turnovers_total": agg["turnovers_total"],
            "double_doubles": agg["double_doubles"],
            "triple_doubles": agg["triple_doubles"],
            "quadruple_doubles": agg["quadruple_doubles"],
            "field_goals_percentage": safe_ratio(agg["field_goals_made_total"], agg["field_goals_attempted_total"]),
            "three_pointers_percentage": safe_ratio(
                agg["three_pointers_made_total"], agg["three_pointers_attempted_total"]
            ),
            "free_throws_percentage": safe_ratio(agg["free_throws_made_total"], agg["free_throws_attempted_total"]),
            "points_per_game": safe_ratio(agg["points_total"], agg["games_played"]),
            "assists_per_game": safe_ratio(agg["assists_total"], agg["games_played"]),
            "rebounds_per_game": safe_ratio(agg["rebounds_total"], agg["games_played"]),
            "rebounds_offensive_total": agg["rebounds_offensive_total"],
            "rebounds_defensive_total": agg["rebounds_defensive_total"],
            "field_goals_made_total": agg["field_goals_made_total"],
            "field_goals_attempted_total": agg["field_goals_attempted_total"],
            "three_pointers_made_total": agg["three_pointers_made_total"],
            "three_pointers_attempted_total": agg["three_pointers_attempted_total"],
            "free_throws_made_total": agg["free_throws_made_total"],
            "free_throws_attempted_total": agg["free_throws_attempted_total"],
            "points_fast_break_total": agg["points_fast_break_total"],
            "points_in_the_paint_total": agg["points_in_the_paint_total"],
            "points_second_chance_total": agg["points_second_chance_total"],
            "fouls_offensive_total": agg["fouls_offensive_total"],
            "fouls_drawn_total": agg["fouls_drawn_total"],
            "fouls_personal_total": agg["fouls_personal_total"],
            "fouls_technical_total": agg["fouls_technical_total"],
            "raw_plus_value_total": agg["raw_plus_value_total"],
            "raw_minus_value_total": agg["raw_minus_value_total"],
            "plus_minus_points_total": agg["plus_minus_points_total"],
            "possessions_total": (
                agg["offensive_possessions_total"] + agg["defensive_possessions_total"]
            ),
        }
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row.get("person_id") if row.get("person_id") is not None else -1,
            row.get("season_start_year") if row.get("season_start_year") is not None else -1,
            row.get("raw_season_type_code") or "",
        )
    )
    return rows


def finalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    for index, row in enumerate(rows, start=1):
        row["agg_player_season_sk"] = index
        row["record_source"] = RECORD_SOURCE
        row["created_at_utc"] = run_ts
        row["updated_at_utc"] = run_ts
    return rows


def main() -> None:
    s3_client = boto3.client("s3")

    fact_table = read_parquet_table_from_s3(s3_client, FACT_SOURCE_KEY, FACT_REQUIRED_COLUMNS)
    team_fact_table = read_parquet_table_from_s3(s3_client, TEAM_FACT_SOURCE_KEY, TEAM_FACT_REQUIRED_COLUMNS)
    dim_player_table = read_parquet_table_from_s3(s3_client, DIM_PLAYER_SOURCE_KEY, DIM_PLAYER_REQUIRED_COLUMNS)
    dim_team_table = read_parquet_table_from_s3(s3_client, DIM_TEAM_SOURCE_KEY, DIM_TEAM_REQUIRED_COLUMNS)
    player_game_possession_context_table = read_parquet_table_from_s3(
        s3_client,
        PLAYER_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        PLAYER_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS,
    )
    rows = build_agg_rows(
        fact_table,
        build_team_game_result_map(team_fact_table),
        build_current_player_attrs_map(dim_player_table),
        build_current_team_attrs_map(dim_team_table),
        build_player_game_possession_map_from_table(player_game_possession_context_table),
    )
    write_parquet_to_s3(finalize_rows(rows), TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
