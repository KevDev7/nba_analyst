"""Purpose: Build semantic_gold team_season as a silver-first team season aggregate object.
Inputs: Silver team-game rows plus silver game/schedule context.
Outputs: One semantic team_season row per (team_id, season_year, season_type).
Next file: deploy_semantic_gold_tables.py publishes the expanded semantic object surface.
"""

from __future__ import annotations

import boto3
import pyarrow as pa
from dotenv import load_dotenv

from pipelines.athena.transform.gold.gold_transform_helpers import (
    S3_BUCKET,
    read_parquet_table_from_s3,
    safe_ratio,
    to_float_or_none,
    to_int_or_none,
    to_positive_int_or_none,
    to_str_or_none,
    write_parquet_to_s3,
)
from pipelines.athena.transform.gold.transform_to_dim_game_parquet import (
    BOXSCORE_REQUIRED_COLUMNS,
    BOXSCORE_SOURCE_KEY,
    SCHEDULE_REQUIRED_COLUMNS,
    SCHEDULE_SOURCE_KEY,
)

from .contracts import TEAM_SEASON_SCHEMA
from .transform_to_team_game_parquet import (
    TEAM_GAME_REQUIRED_COLUMNS,
    TEAM_GAME_SOURCE_KEY,
    build_team_game_rows_from_tables,
)

load_dotenv(override=True)

DESTINATION_KEY = "semantic_gold/team_season/team_season.parquet"
TEAM_GAME_POSSESSION_CONTEXT_SOURCE_KEY = "silver/team_game_possession_context.parquet"
TEAM_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "offensive_possessions",
    "defensive_possessions",
]
TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY = "silver/team_game_defensive_shot_context.parquet"
TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS = [
    "game_id",
    "team_id",
    "opponent_two_point_attempts",
]


def build_team_game_possession_map_from_table(
    team_game_possession_context_table: pa.Table,
) -> dict[tuple[str, int], dict[str, float]]:
    possession_map: dict[tuple[str, int], dict[str, float]] = {}
    for row in team_game_possession_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        possession_map[(game_id, team_id)] = {
            "offensive_possessions_total": to_float_or_none(row.get("offensive_possessions")) or 0.0,
            "defensive_possessions_total": to_float_or_none(row.get("defensive_possessions")) or 0.0,
        }
    return possession_map


def build_team_game_defensive_shot_context_map_from_table(
    team_game_defensive_shot_context_table: pa.Table,
) -> dict[tuple[str, int], dict[str, float]]:
    shot_context_map: dict[tuple[str, int], dict[str, float]] = {}
    for row in team_game_defensive_shot_context_table.to_pylist():
        game_id = to_str_or_none(row.get("game_id"))
        team_id = to_int_or_none(row.get("team_id"))
        if game_id is None or team_id is None:
            continue
        shot_context_map[(game_id, team_id)] = {
            "opponent_two_point_attempts_total": to_float_or_none(row.get("opponent_two_point_attempts")) or 0.0,
        }
    return shot_context_map


def build_team_season_rows_from_team_game_rows(
    team_game_rows: list[dict[str, object]],
    team_game_possession_map: dict[tuple[str, int], dict[str, float]] | None = None,
    team_game_shot_context_map: dict[tuple[str, int], dict[str, float]] | None = None,
) -> list[dict[str, object]]:
    def _rounded_ratio(
        numerator: object,
        denominator: object,
        *,
        scale: float = 1.0,
        digits: int = 1,
    ) -> float | None:
        ratio = safe_ratio(numerator, denominator)
        return round(scale * ratio, digits) if ratio is not None else None

    grouped: dict[tuple[int, str, str], dict[str, object]] = {}

    for row in team_game_rows:
        team_id = to_positive_int_or_none(row.get("team_id"))
        season_year = to_str_or_none(row.get("season_year"))
        season_type = to_str_or_none(row.get("season_type"))
        if team_id is None or season_year is None or season_type is None:
            continue

        key = (team_id, season_year, season_type)
        current = grouped.setdefault(
            key,
            {
                "team_id": team_id,
                "season_year": season_year,
                "season_type": season_type,
                "games_played": 0,
                "wins": 0,
                "losses": 0,
                "minutes_played_total": 0.0,
                "assists_total": 0,
                "blocks_total": 0,
                "turnovers_total": 0,
                "steals_total": 0,
                "field_goals_attempted_total": 0,
                "field_goals_made_total": 0,
                "three_pointers_attempted_total": 0,
                "three_pointers_made_total": 0,
                "two_pointers_attempted_total": 0,
                "two_pointers_made_total": 0,
                "free_throws_made_total": 0,
                "free_throws_attempted_total": 0,
                "offensive_fouls_committed_total": 0,
                "fouls_drawn_total": 0,
                "personal_fouls_committed_total": 0,
                "technical_fouls_committed_total": 0,
                "rebounds_offensive_total": 0,
                "rebounds_defensive_total": 0,
                "rebounds_total": 0,
                "opponent_rebounds_offensive_total": 0,
                "opponent_rebounds_defensive_total": 0,
                "opponent_rebounds_total": 0,
                "score_total": 0,
                "points_against_total": 0,
                "offensive_possessions_total": 0.0,
                "defensive_possessions_total": 0.0,
                "opponent_two_point_attempts_total": 0.0,
            },
        )

        current["games_played"] = to_int_or_none(current.get("games_played")) or 0
        current["games_played"] += 1
        win_loss_result = row.get("win_loss_result")
        current["wins"] = to_int_or_none(current.get("wins")) or 0
        current["wins"] += 1 if win_loss_result == "win" else 0
        current["losses"] = to_int_or_none(current.get("losses")) or 0
        current["losses"] += 1 if win_loss_result == "loss" else 0
        current["minutes_played_total"] = (
            to_float_or_none(current.get("minutes_played_total")) or 0.0
        ) + (to_float_or_none(row.get("minutes_played")) or 0.0)
        for field, source_field in (
            ("assists_total", "assists"),
            ("blocks_total", "blocks"),
            ("turnovers_total", "turnovers"),
            ("steals_total", "steals"),
            ("field_goals_attempted_total", "field_goals_attempted"),
            ("field_goals_made_total", "field_goals_made"),
            ("three_pointers_attempted_total", "three_pointers_attempted"),
            ("three_pointers_made_total", "three_pointers_made"),
            ("two_pointers_attempted_total", "two_pointers_attempted"),
            ("two_pointers_made_total", "two_pointers_made"),
            ("free_throws_made_total", "free_throws_made"),
            ("free_throws_attempted_total", "free_throws_attempted"),
            ("offensive_fouls_committed_total", "offensive_fouls_committed"),
            ("fouls_drawn_total", "fouls_drawn"),
            ("personal_fouls_committed_total", "personal_fouls_committed"),
            ("technical_fouls_committed_total", "technical_fouls_committed"),
            ("rebounds_offensive_total", "offensive_rebounds"),
            ("rebounds_defensive_total", "defensive_rebounds"),
            ("rebounds_total", "total_rebounds"),
            ("opponent_rebounds_offensive_total", "opponent_offensive_rebounds"),
            ("opponent_rebounds_defensive_total", "opponent_defensive_rebounds"),
            ("opponent_rebounds_total", "opponent_total_rebounds"),
            ("score_total", "score"),
            ("points_against_total", "opponent_score"),
        ):
            current[field] = to_int_or_none(current.get(field)) or 0
            current[field] += to_int_or_none(row.get(source_field)) or 0
        game_id = to_str_or_none(row.get("game_id"))
        if game_id is not None:
            possession_stats = (team_game_possession_map or {}).get((game_id, team_id))
            if possession_stats is not None:
                current["offensive_possessions_total"] = (
                    to_float_or_none(current.get("offensive_possessions_total")) or 0.0
                ) + (to_float_or_none(possession_stats.get("offensive_possessions_total")) or 0.0)
                current["defensive_possessions_total"] = (
                    to_float_or_none(current.get("defensive_possessions_total")) or 0.0
                ) + (to_float_or_none(possession_stats.get("defensive_possessions_total")) or 0.0)
            shot_context_stats = (team_game_shot_context_map or {}).get((game_id, team_id))
            if shot_context_stats is not None:
                current["opponent_two_point_attempts_total"] = (
                    to_float_or_none(current.get("opponent_two_point_attempts_total")) or 0.0
                ) + (to_float_or_none(shot_context_stats.get("opponent_two_point_attempts_total")) or 0.0)

    season_rows: list[dict[str, object]] = []
    for key in sorted(grouped):
        aggregate = grouped[key]
        games_played = to_int_or_none(aggregate.get("games_played")) or 0
        wins = to_int_or_none(aggregate.get("wins")) or 0
        losses = to_int_or_none(aggregate.get("losses")) or 0
        minutes_played_total = to_float_or_none(aggregate.get("minutes_played_total")) or 0.0
        assists_total = to_int_or_none(aggregate.get("assists_total")) or 0
        blocks_total = to_int_or_none(aggregate.get("blocks_total")) or 0
        turnovers_total = to_int_or_none(aggregate.get("turnovers_total")) or 0
        steals_total = to_int_or_none(aggregate.get("steals_total")) or 0
        field_goals_attempted_total = to_int_or_none(aggregate.get("field_goals_attempted_total")) or 0
        field_goals_made_total = to_int_or_none(aggregate.get("field_goals_made_total")) or 0
        three_pointers_attempted_total = to_int_or_none(aggregate.get("three_pointers_attempted_total")) or 0
        three_pointers_made_total = to_int_or_none(aggregate.get("three_pointers_made_total")) or 0
        two_pointers_attempted_total = to_int_or_none(aggregate.get("two_pointers_attempted_total")) or 0
        two_pointers_made_total = to_int_or_none(aggregate.get("two_pointers_made_total")) or 0
        free_throws_made_total = to_int_or_none(aggregate.get("free_throws_made_total")) or 0
        free_throws_attempted_total = to_int_or_none(aggregate.get("free_throws_attempted_total")) or 0
        offensive_fouls_committed_total = to_int_or_none(
            aggregate.get("offensive_fouls_committed_total")
        ) or 0
        fouls_drawn_total = to_int_or_none(aggregate.get("fouls_drawn_total")) or 0
        personal_fouls_committed_total = to_int_or_none(
            aggregate.get("personal_fouls_committed_total")
        ) or 0
        technical_fouls_committed_total = to_int_or_none(
            aggregate.get("technical_fouls_committed_total")
        ) or 0
        rebounds_offensive_total = to_int_or_none(aggregate.get("rebounds_offensive_total")) or 0
        rebounds_defensive_total = to_int_or_none(aggregate.get("rebounds_defensive_total")) or 0
        rebounds_total = to_int_or_none(aggregate.get("rebounds_total")) or 0
        opponent_rebounds_offensive_total = to_int_or_none(aggregate.get("opponent_rebounds_offensive_total")) or 0
        opponent_rebounds_defensive_total = to_int_or_none(aggregate.get("opponent_rebounds_defensive_total")) or 0
        opponent_rebounds_total = to_int_or_none(aggregate.get("opponent_rebounds_total")) or 0
        score_total = to_int_or_none(aggregate.get("score_total")) or 0
        points_against_total = to_int_or_none(aggregate.get("points_against_total")) or 0
        offensive_possessions_total = to_float_or_none(aggregate.get("offensive_possessions_total")) or 0.0
        defensive_possessions_total = to_float_or_none(aggregate.get("defensive_possessions_total")) or 0.0
        opponent_two_point_attempts_total = (
            to_float_or_none(aggregate.get("opponent_two_point_attempts_total")) or 0.0
        )
        true_shooting_denominator = 2.0 * (
            field_goals_attempted_total + (0.44 * free_throws_attempted_total)
        )
        hybrid_standard_possessions = (
            (offensive_possessions_total + defensive_possessions_total) / 2.0
            if (offensive_possessions_total + defensive_possessions_total) > 0
            else None
        )
        season_rows.append(
            {
                "games_played": games_played,
                "wins": wins,
                "losses": losses,
                "win_percentage": round(safe_ratio(wins, games_played), 3)
                if games_played > 0
                else None,
                "team_id": aggregate["team_id"],
                "season_year": aggregate["season_year"],
                "season_type": aggregate["season_type"],
                "minutes": int(round(minutes_played_total / 5.0))
                if minutes_played_total > 0
                else None,
                "minutes_per_game": _rounded_ratio(minutes_played_total / 5.0, games_played),
                "points_total": score_total,
                "points_per_game": _rounded_ratio(score_total, games_played),
                "assists_total": assists_total,
                "assists_per_game": _rounded_ratio(assists_total, games_played),
                "turnovers_total": turnovers_total,
                "turnovers_per_game": _rounded_ratio(turnovers_total, games_played),
                "steals_total": steals_total,
                "steals_per_game": _rounded_ratio(steals_total, games_played),
                "blocks_total": blocks_total,
                "blocks_per_game": _rounded_ratio(blocks_total, games_played),
                "rebounds_total": rebounds_total,
                "rebounds_per_game": _rounded_ratio(rebounds_total, games_played),
                "offensive_rebounds_total": rebounds_offensive_total,
                "offensive_rebounds_per_game": _rounded_ratio(rebounds_offensive_total, games_played),
                "defensive_rebounds_total": rebounds_defensive_total,
                "defensive_rebounds_per_game": _rounded_ratio(rebounds_defensive_total, games_played),
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
                "three_pointers_attempted_per_game": _rounded_ratio(three_pointers_attempted_total, games_played),
                "three_pointers_percentage": _rounded_ratio(
                    three_pointers_made_total,
                    three_pointers_attempted_total,
                    scale=100.0,
                ),
                "two_pointers_made_total": two_pointers_made_total,
                "two_pointers_made_per_game": _rounded_ratio(two_pointers_made_total, games_played),
                "two_pointers_attempted_total": two_pointers_attempted_total,
                "two_pointers_attempted_per_game": _rounded_ratio(two_pointers_attempted_total, games_played),
                "two_pointers_percentage": _rounded_ratio(
                    two_pointers_made_total,
                    two_pointers_attempted_total,
                    scale=100.0,
                ),
                "free_throws_made_total": free_throws_made_total,
                "free_throws_made_per_game": _rounded_ratio(free_throws_made_total, games_played),
                "free_throws_attempted_total": free_throws_attempted_total,
                "free_throws_attempted_per_game": _rounded_ratio(free_throws_attempted_total, games_played),
                "free_throws_percentage": _rounded_ratio(
                    free_throws_made_total,
                    free_throws_attempted_total,
                    scale=100.0,
                ),
                "offensive_fouls_committed_total": offensive_fouls_committed_total,
                "fouls_drawn_total": fouls_drawn_total,
                "personal_fouls_committed_total": personal_fouls_committed_total,
                "personal_fouls_committed_per_game": _rounded_ratio(
                    personal_fouls_committed_total, games_played
                ),
                "technical_fouls_committed_total": technical_fouls_committed_total,
                "possessions": int(round(hybrid_standard_possessions))
                if hybrid_standard_possessions is not None
                else None,
                "offensive_possessions": round(offensive_possessions_total, 1)
                if offensive_possessions_total > 0
                else None,
                "defensive_possessions": round(defensive_possessions_total, 1)
                if defensive_possessions_total > 0
                else None,
                "pace": round(hybrid_standard_possessions * 240.0 / minutes_played_total, 1)
                if hybrid_standard_possessions is not None and minutes_played_total > 0
                else None,
                "offensive_rating": round(score_total * 100.0 / hybrid_standard_possessions, 1)
                if hybrid_standard_possessions is not None
                else None,
                "defensive_rating": round(points_against_total * 100.0 / hybrid_standard_possessions, 1)
                if hybrid_standard_possessions is not None
                else None,
                "net_rating": round(
                    (score_total * 100.0 / hybrid_standard_possessions)
                    - (points_against_total * 100.0 / hybrid_standard_possessions),
                    1,
                )
                if hybrid_standard_possessions is not None
                else None,
                "steal_percentage": _rounded_ratio(
                    steals_total,
                    defensive_possessions_total,
                    scale=100.0,
                ),
                "block_percentage": _rounded_ratio(
                    blocks_total,
                    opponent_two_point_attempts_total,
                    scale=100.0,
                ),
                "assist_percentage": _rounded_ratio(assists_total, field_goals_made_total, scale=100.0),
                "assist_to_turnover_ratio": _rounded_ratio(
                    assists_total, turnovers_total, digits=2
                ),
                "offensive_rebound_percentage": _rounded_ratio(
                    rebounds_offensive_total,
                    rebounds_offensive_total + opponent_rebounds_defensive_total,
                    scale=100.0,
                ),
                "defensive_rebound_percentage": _rounded_ratio(
                    rebounds_defensive_total,
                    rebounds_defensive_total + opponent_rebounds_offensive_total,
                    scale=100.0,
                ),
                "rebound_percentage": _rounded_ratio(
                    rebounds_total,
                    rebounds_total + opponent_rebounds_total,
                    scale=100.0,
                ),
                "effective_field_goal_percentage": _rounded_ratio(
                    field_goals_made_total + (0.5 * three_pointers_made_total),
                    field_goals_attempted_total,
                    scale=100.0,
                ),
                "three_point_attempt_rate": _rounded_ratio(
                    three_pointers_attempted_total,
                    field_goals_attempted_total,
                    digits=3,
                ),
                "free_throw_attempt_rate": _rounded_ratio(
                    free_throws_attempted_total,
                    field_goals_attempted_total,
                    digits=3,
                ),
                "true_shooting_percentage": _rounded_ratio(
                    score_total,
                    true_shooting_denominator,
                    scale=100.0,
                ),
            }
        )
    return season_rows


def build_team_season_rows_from_tables(
    team_game_table: pa.Table,
    box_table: pa.Table,
    schedule_table: pa.Table,
    team_game_possession_context_table: pa.Table | None = None,
    team_game_defensive_shot_context_table: pa.Table | None = None,
) -> list[dict[str, object]]:
    team_game_rows = build_team_game_rows_from_tables(
        team_game_table, box_table, schedule_table
    )
    return build_team_season_rows_from_team_game_rows(
        team_game_rows,
        build_team_game_possession_map_from_table(team_game_possession_context_table)
        if team_game_possession_context_table is not None
        else None,
        build_team_game_defensive_shot_context_map_from_table(
            team_game_defensive_shot_context_table
        )
        if team_game_defensive_shot_context_table is not None
        else None,
    )


def main() -> None:
    s3_client = boto3.client("s3")
    team_game_table = read_parquet_table_from_s3(
        s3_client, TEAM_GAME_SOURCE_KEY, TEAM_GAME_REQUIRED_COLUMNS
    )
    box_table = read_parquet_table_from_s3(
        s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS
    )
    schedule_table = read_parquet_table_from_s3(
        s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS
    )
    team_game_possession_context_table = read_parquet_table_from_s3(
        s3_client,
        TEAM_GAME_POSSESSION_CONTEXT_SOURCE_KEY,
        TEAM_GAME_POSSESSION_CONTEXT_REQUIRED_COLUMNS,
    )
    team_game_defensive_shot_context_table = read_parquet_table_from_s3(
        s3_client,
        TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_SOURCE_KEY,
        TEAM_GAME_DEFENSIVE_SHOT_CONTEXT_REQUIRED_COLUMNS,
    )
    rows = build_team_season_rows_from_tables(
        team_game_table,
        box_table,
        schedule_table,
        team_game_possession_context_table,
        team_game_defensive_shot_context_table,
    )
    write_parquet_to_s3(rows, TEAM_SEASON_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
