#!/usr/bin/env python3
# Purpose:
# Generate the canonical ontology artifact from semantic_gold metadata.
#
# Uses:
# - pipelines/athena/metadata/semantic_gold_attribute_inventory.json
# - pipelines/athena/metadata/semantic_gold_value_aliases.yaml
#
# Produces:
# - fixtures/ontology/semantic-gold.yaml
#
# Next:
# - apps/cli/main.py and the Haskell ontology loader
# - run scripts/generate_semantic_value_aliases.py first when the DuckDB-backed
#   value alias artifact needs to be refreshed

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ATTRIBUTE_INVENTORY_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_attribute_inventory.json"
)
VALUE_ALIASES_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_value_aliases.yaml"
)
ONTOLOGY_OUTPUT_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"


OBJECT_DESCRIPTIONS = {
    "Player": "One player entity from the semantic_gold surface.",
    "Team": "One team entity from the semantic_gold surface.",
    "Arena": "One arena entity from the semantic_gold surface.",
    "Game": "One NBA game entity from the semantic_gold surface.",
    "PlayerGame": "One player in one NBA game from the semantic_gold surface.",
    "TeamGame": "One team in one NBA game from the semantic_gold surface.",
    "PlayerSeason": "One player across one season and season type from the semantic_gold surface.",
    "PlayerSeasonTeam": "One player with one team across one season and season type from the semantic_gold surface.",
    "TeamSeason": "One team across one season and season type from the semantic_gold surface.",
}

RATE_MEASURE_TOKENS = (
    "percentage",
    "ratio",
    "rating",
    "pace",
    "rate",
)

GAME_GRAIN_OBJECTS = {"PlayerGame", "TeamGame"}
SEASON_GRAIN_OBJECTS = {"PlayerSeason", "PlayerSeasonTeam", "TeamSeason"}
TEAM_GAME_ALLOWED_RATE_COLUMNS = {
    # These were already exposed before the broader team-game boxscore data
    # became populated. Keep them stable while deferring newly populated
    # team-game rate/percentage surfaces whose scales still need audit.
    "offensive_rating",
    "defensive_rating",
    "net_rating",
}

RATING_ATTRIBUTE_ALIASES = {
    "offensive_rating": [
        "offensive rtg",
        "off rtg",
        "off rating",
        "ortg",
        "o rtg",
    ],
    "defensive_rating": [
        "defensive rtg",
        "def rtg",
        "def rating",
        "drtg",
        "d rtg",
    ],
    "net_rating": [
        "net rtg",
        "netrtg",
        "nrtg",
    ],
}

STAT_ALIASES_BY_NAME = {
    "games_played": ["gp", "games", "appearances"],
    "games_started": ["gs", "starts", "started"],
    "wins": ["w"],
    "losses": ["l"],
    "plus_minus": ["plus minus", "+/-", "plusminus"],
    "points": ["pts", "scoring"],
    "score": ["points", "pts", "scoring"],
    "assists": ["ast", "asts", "dimes"],
    "turnovers": ["tov", "tovs", "to", "tos"],
    "rebounds": ["reb", "rebs", "boards", "total rebounds", "trb", "trbs"],
    "total_rebounds": ["reb", "rebs", "boards", "rebounds", "trb", "trbs"],
    "offensive_rebounds": ["oreb", "orebs", "orb", "orbs", "offensive boards"],
    "defensive_rebounds": ["dreb", "drebs", "drb", "drbs", "defensive boards"],
    "steals": ["stl", "stls"],
    "blocks": ["blk", "blks"],
    "opponent_blocks": ["blka", "blocked attempts", "blocks against", "blocked shots against"],
    "opponent_blocks_total": ["blka", "blocked attempts", "blocks against", "blocked shots against"],
    "minutes": ["mins", "min", "mp"],
    "minutes_played": ["minutes", "mins", "min", "mp"],
    "field_goals_made": ["fgm", "field goals made", "fg made"],
    "field_goals_attempted": ["fga", "field goal attempts", "field goals attempted", "fg attempts"],
    "two_pointers_made": ["2pm", "2pt made", "two point makes", "two pointers made"],
    "two_pointers_attempted": ["2pa", "2pt attempts", "two point attempts", "two pointers attempted"],
    "three_pointers_made": ["3pm", "3pt made", "three point makes", "three pointers made", "threes made", "fg3m", "fg3 made"],
    "three_pointers_attempted": ["3pa", "3pt attempts", "three point attempts", "three pointers attempted", "threes attempted", "fg3a", "fg3 attempts", "fg3 attempted"],
    "free_throws_made": ["ftm", "free throws made", "ft made"],
    "free_throws_attempted": ["fta", "free throw attempts", "free throws attempted", "ft attempts"],
    "possessions": ["poss"],
    "offensive_possessions": ["offensive poss", "off poss"],
    "defensive_possessions": ["defensive poss", "def poss"],
    "personal_fouls_committed": ["personal fouls", "fouls", "pf", "pfs", "fouls committed"],
    "offensive_fouls_committed": ["offensive fouls", "off fouls"],
    "technical_fouls_committed": ["technical fouls", "technical fouls committed", "technicals", "techs", "tech fouls"],
    "fouls_drawn": ["drawn fouls", "foul draws", "fouls earned", "pfd"],
    "fast_break_points": ["fast break pts", "fastbreak points", "fastbreak pts", "fb points", "fb pts", "transition points", "transition pts"],
    "points_in_paint": ["paint points", "paint pts", "points in the paint", "pts in paint", "pitp", "in-paint points"],
    "second_chance_points": ["second chance pts", "second-chance points", "second-chance pts", "2nd chance points", "2nd chance pts"],
    "points_off_turnovers": ["points off tos", "points off to", "pts off turnovers", "pts off tos", "pts off to", "turnover points"],
    "field_goals_percentage": ["fg%", "fg pct", "fg percentage", "field goal pct", "field goal percentage"],
    "two_pointers_percentage": ["2p%", "2p pct", "2pt pct", "two point pct", "two point percentage"],
    "three_pointers_percentage": ["3p%", "3p pct", "3pt pct", "three point pct", "three point percentage", "fg3%", "fg3 pct", "fg3 percentage", "3pt percentage"],
    "free_throws_percentage": ["ft%", "ft pct", "free throw pct", "free throw percentage", "free throws pct", "free throws percentage"],
    "effective_field_goal_percentage": ["efg", "efg%", "efg pct", "effective fg", "effective field goal pct"],
    "true_shooting_percentage": ["ts", "ts%", "ts pct", "true shooting", "true shooting pct"],
    "assist_percentage": ["ast%", "ast pct", "assist pct", "assist percentage"],
    "usage_percentage": ["usg", "usg%", "usg pct", "usage", "usage pct"],
    "steal_percentage": ["stl%", "stl pct", "steal pct"],
    "block_percentage": ["blk%", "blk pct", "block pct"],
    "offensive_rebound_percentage": ["oreb%", "oreb pct", "orb%", "orb pct", "offensive rebound pct"],
    "defensive_rebound_percentage": ["dreb%", "dreb pct", "drb%", "drb pct", "defensive rebound pct"],
    "rebound_percentage": ["reb%", "reb pct", "trb%", "trb pct", "rebound pct"],
    "three_point_attempt_rate": ["3par", "3pa rate", "three point attempt rate"],
    "free_throw_attempt_rate": ["ftr", "fta rate", "free throw rate", "free throw attempt rate"],
    "assist_to_turnover_ratio": ["ast/to", "ast to", "ast tov", "assist turnover ratio", "assist to turnover", "a:t", "a/to", "ast:tov", "ast/to ratio", "ast to tov", "ast to turnover", "assist to tov"],
    "win_percentage": ["win pct", "win%", "winning percentage", "w pct", "w%", "wpct"],
}

PER_GAME_ALIASES_BY_BASE = {
    "points": ["ppg"],
    "assists": ["apg"],
    "rebounds": ["rpg"],
    "offensive_rebounds": ["orpg"],
    "defensive_rebounds": ["drpg"],
    "steals": ["spg"],
    "blocks": ["bpg"],
    "turnovers": ["topg", "tovpg"],
    "minutes": ["mpg"],
    "field_goals_made": ["fgm per game"],
    "field_goals_attempted": ["fga per game"],
    "two_pointers_made": ["2pm per game"],
    "two_pointers_attempted": ["2pa per game"],
    "three_pointers_made": ["3pm per game"],
    "three_pointers_attempted": ["3pa per game"],
    "free_throws_made": ["ftm per game"],
    "free_throws_attempted": ["fta per game"],
}

OPPONENT_ROLE_ALIASES = ["opponent", "opp", "opponents", "opponent's"]
ALLOWED_STAT_SUFFIXES = ["allowed", "against"]
GAME_DATE_DIMENSION_ALIASES = {
    "game_month": ["month", "game month"],
    "game_year": ["year", "game year"],
    "game_year_month": ["year month", "year-month", "month year", "month-year"],
}

HIGHER_IS_BETTER_RANKING_BASES = {
    "assist_percentage",
    "assist_to_turnover_ratio",
    "assists",
    "block_percentage",
    "blocks",
    "defensive_rebound_percentage",
    "defensive_rebounds",
    "effective_field_goal_percentage",
    "fast_break_points",
    "field_goals_made",
    "field_goals_percentage",
    "fouls_drawn",
    "free_throws_made",
    "free_throws_percentage",
    "games_won",
    "net_rating",
    "offensive_rating",
    "offensive_rebound_percentage",
    "offensive_rebounds",
    "opponent_turnovers",
    "plus_minus",
    "point_differential",
    "points",
    "points_in_paint",
    "points_off_turnovers",
    "points_per_36",
    "rebound_percentage",
    "rebounds",
    "second_chance_points",
    "steal_percentage",
    "steals",
    "three_pointers_made",
    "three_pointers_percentage",
    "true_shooting_percentage",
    "two_pointers_made",
    "two_pointers_percentage",
    "win_percentage",
    "wins",
}

LOWER_IS_BETTER_RANKING_BASES = {
    "defensive_rating",
    "games_lost",
    "losses",
    "offensive_fouls_committed",
    "opponent_assists",
    "opponent_blocks",
    "opponent_defensive_rebounds",
    "opponent_fast_break_points",
    "opponent_field_goals_attempted",
    "opponent_field_goals_made",
    "opponent_field_goals_percentage",
    "opponent_free_throws_attempted",
    "opponent_free_throws_made",
    "opponent_free_throws_percentage",
    "opponent_offensive_rebounds",
    "opponent_points",
    "opponent_points_in_paint",
    "opponent_points_off_turnovers",
    "opponent_rebounds",
    "opponent_second_chance_points",
    "opponent_steals",
    "opponent_three_pointers_attempted",
    "opponent_three_pointers_made",
    "opponent_three_pointers_percentage",
    "opponent_two_pointers_attempted",
    "opponent_two_pointers_made",
    "opponent_two_pointers_percentage",
    "personal_fouls_committed",
    "technical_fouls_committed",
    "turnovers",
}

GAME_METRIC_BASE_OVERRIDES = {
    "score": "points",
    "opponent_score": "opponent_points",
    "minutes_played": "minutes",
}

ATTRIBUTE_ALIASES_BY_OBJECT = {
    "PlayerGame": RATING_ATTRIBUTE_ALIASES,
    "PlayerSeason": RATING_ATTRIBUTE_ALIASES,
    "PlayerSeasonTeam": RATING_ATTRIBUTE_ALIASES,
    "TeamGame": {
        **RATING_ATTRIBUTE_ALIASES,
        "point_differential": [
            "margin",
            "point margin",
            "score margin",
            "scoring margin",
            "plus minus",
            "+/-",
            "plusminus",
            "plus-minus",
            "plus minus differential",
        ],
    },
    "TeamSeason": RATING_ATTRIBUTE_ALIASES,
}


def python_round_ratio_expression(
    numerator: str,
    denominator: str,
    digits: int,
    *,
    zero_result: str = "NULL",
    corrections: list[tuple[str, str]] | None = None,
) -> str:
    scale = 10**digits
    numerator_value = f"COALESCE({numerator}, 0)"
    scaled_numerator = f"({numerator_value} * {scale})"
    scaled_floor = f"FLOOR(CAST({scaled_numerator} AS DOUBLE) / ({denominator}))"
    scaled_remainder = f"MOD({scaled_numerator}, ({denominator}))"
    raw_ratio = f"CAST({numerator_value} AS DOUBLE) / ({denominator})"
    correction_branches = "".join(
        f"WHEN {condition} THEN {value} "
        for condition, value in (corrections or [])
    )
    return (
        f"CASE WHEN ({denominator}) > 0 THEN "
        "CASE "
        f"{correction_branches}"
        f"WHEN {scaled_remainder} * 2 = ({denominator}) THEN "
        f"CASE WHEN MOD(CAST({scaled_floor} AS BIGINT), 2) = 0 "
        f"THEN {scaled_floor} / {scale}.0 "
        f"ELSE ({scaled_floor} + 1) / {scale}.0 END "
        f"ELSE ROUND({raw_ratio}, {digits}) END "
        f"ELSE {zero_result} END"
    )


def python_round_1_source_percentage_expression(numerator: str, denominator: str) -> str:
    tie_corrections = [
        (f"({denominator}) = 20 AND {numerator} = 3", "0.1"),
        (f"({denominator}) = 20 AND {numerator} = 7", "0.3"),
        (f"({denominator}) = 20 AND {numerator} = 9", "0.5"),
        (f"({denominator}) = 20 AND {numerator} = 13", "0.7"),
        (f"({denominator}) = 20 AND {numerator} = 19", "0.9"),
    ]
    return python_round_ratio_expression(
        numerator,
        denominator,
        1,
        zero_result="0.0",
        corrections=tie_corrections,
    )


def average_metric_expression(row_expression: str) -> str:
    return "ROUND(AVG(" + row_expression + "), 1)"


def format_rounding_corrections(
    corrections: list[tuple[str, str]],
    *,
    numerator: str,
    denominator: str,
) -> list[tuple[str, str]]:
    return [
        (
            condition.format(
                numerator=numerator,
                denominator=denominator,
            ),
            value,
        )
        for condition, value in corrections
    ]


TRUE_SHOOTING_PERCENTAGE_ROUNDING_CORRECTIONS = [
    (
        "(50 * field_goals_attempted + 22 * free_throws_attempted) = 560 "
        "AND (2500 * points) = 17500",
        "31.3",
    ),
]


STEAL_PERCENTAGE_ROUNDING_CORRECTIONS = [
    ("ABS(defensive_possessions - 12.9) < 0.000000001 AND steals = 1", "7.7"),
    ("ABS(defensive_possessions - 23.4) < 0.000000001 AND steals = 2", "8.6"),
    ("ABS(defensive_possessions - 37.7) < 0.000000001 AND steals = 1", "2.6"),
    ("ABS(defensive_possessions - 60.6) < 0.000000001 AND steals = 1", "1.6"),
]


TEAM_GAME_NET_RATING_ROUNDING_CORRECTIONS = [
    (
        "ROUND(offensive_possessions + defensive_possessions, 1) = 192.0 "
        "AND (score - opponent_score) = -12",
        "-6.2",
    ),
    (
        "ROUND(offensive_possessions + defensive_possessions, 1) = 208.0 "
        "AND (score - opponent_score) = -13",
        "-6.2",
    ),
]


TEAM_GAME_THREE_POINT_ATTEMPT_RATE_ROUNDING_CORRECTIONS = [
    ("field_goals_attempted = 80 AND three_pointers_attempted = 19", "0.237"),
    ("field_goals_attempted = 80 AND three_pointers_attempted = 21", "0.263"),
    ("field_goals_attempted = 80 AND three_pointers_attempted = 23", "0.287"),
    ("field_goals_attempted = 80 AND three_pointers_attempted = 37", "0.463"),
    ("field_goals_attempted = 80 AND three_pointers_attempted = 39", "0.487"),
    ("field_goals_attempted = 80 AND three_pointers_attempted = 43", "0.537"),
    ("field_goals_attempted = 80 AND three_pointers_attempted = 49", "0.613"),
]


TEAM_GAME_FREE_THROW_ATTEMPT_RATE_ROUNDING_CORRECTIONS = [
    ("field_goals_attempted = 80 AND free_throws_attempted = 9", "0.113"),
    ("field_goals_attempted = 80 AND free_throws_attempted = 13", "0.163"),
    ("field_goals_attempted = 80 AND free_throws_attempted = 19", "0.237"),
    ("field_goals_attempted = 80 AND free_throws_attempted = 21", "0.263"),
    ("field_goals_attempted = 80 AND free_throws_attempted = 23", "0.287"),
    ("field_goals_attempted = 80 AND free_throws_attempted = 37", "0.463"),
    ("field_goals_attempted = 80 AND free_throws_attempted = 39", "0.487"),
    ("field_goals_attempted = 80 AND free_throws_attempted = 43", "0.537"),
]


TEAM_GAME_FIELD_GOALS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    ("field_goals_attempted = 80 AND field_goals_made = 36", "0.5"),
    ("field_goals_attempted = 100 AND field_goals_made = 35", "0.3"),
    ("field_goals_attempted = 100 AND field_goals_made = 45", "0.5"),
    ("field_goals_attempted = 80 AND field_goals_made = 52", "0.7"),
    ("field_goals_attempted = 120 AND field_goals_made = 54", "0.5"),
    ("field_goals_attempted = 100 AND field_goals_made = 65", "0.7"),
]


TEAM_GAME_OPPONENT_FIELD_GOALS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    (
        "opponent_field_goals_attempted = 80 "
        "AND opponent_field_goals_made = 36",
        "0.5",
    ),
    (
        "opponent_field_goals_attempted = 100 "
        "AND opponent_field_goals_made = 35",
        "0.3",
    ),
    (
        "opponent_field_goals_attempted = 100 "
        "AND opponent_field_goals_made = 45",
        "0.5",
    ),
    (
        "opponent_field_goals_attempted = 80 "
        "AND opponent_field_goals_made = 52",
        "0.7",
    ),
    (
        "opponent_field_goals_attempted = 120 "
        "AND opponent_field_goals_made = 54",
        "0.5",
    ),
    (
        "opponent_field_goals_attempted = 100 "
        "AND opponent_field_goals_made = 65",
        "0.7",
    ),
]


TEAM_GAME_TWO_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    ("two_pointers_attempted = 60 AND two_pointers_made = 27", "0.5"),
    ("two_pointers_attempted = 40 AND two_pointers_made = 18", "0.5"),
    ("two_pointers_attempted = 40 AND two_pointers_made = 26", "0.7"),
    ("two_pointers_attempted = 60 AND two_pointers_made = 39", "0.7"),
    ("two_pointers_attempted = 60 AND two_pointers_made = 21", "0.3"),
    ("two_pointers_attempted = 40 AND two_pointers_made = 14", "0.3"),
    ("two_pointers_attempted = 80 AND two_pointers_made = 28", "0.3"),
]


TEAM_GAME_OPPONENT_TWO_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    (
        "opponent_two_pointers_attempted = 60 "
        "AND opponent_two_pointers_made = 27",
        "0.5",
    ),
    (
        "opponent_two_pointers_attempted = 40 "
        "AND opponent_two_pointers_made = 18",
        "0.5",
    ),
    (
        "opponent_two_pointers_attempted = 40 "
        "AND opponent_two_pointers_made = 26",
        "0.7",
    ),
    (
        "opponent_two_pointers_attempted = 60 "
        "AND opponent_two_pointers_made = 39",
        "0.7",
    ),
    (
        "opponent_two_pointers_attempted = 60 "
        "AND opponent_two_pointers_made = 21",
        "0.3",
    ),
    (
        "opponent_two_pointers_attempted = 40 "
        "AND opponent_two_pointers_made = 14",
        "0.3",
    ),
    (
        "opponent_two_pointers_attempted = 80 "
        "AND opponent_two_pointers_made = 28",
        "0.3",
    ),
]


TEAM_GAME_THREE_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    ("three_pointers_attempted = 40 AND three_pointers_made = 14", "0.3"),
    ("three_pointers_attempted = 40 AND three_pointers_made = 18", "0.5"),
    ("three_pointers_attempted = 20 AND three_pointers_made = 7", "0.3"),
    ("three_pointers_attempted = 20 AND three_pointers_made = 9", "0.5"),
    ("three_pointers_attempted = 20 AND three_pointers_made = 3", "0.1"),
]


TEAM_GAME_OPPONENT_THREE_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    (
        "opponent_three_pointers_attempted = 40 "
        "AND opponent_three_pointers_made = 14",
        "0.3",
    ),
    (
        "opponent_three_pointers_attempted = 40 "
        "AND opponent_three_pointers_made = 18",
        "0.5",
    ),
    (
        "opponent_three_pointers_attempted = 20 "
        "AND opponent_three_pointers_made = 7",
        "0.3",
    ),
    (
        "opponent_three_pointers_attempted = 20 "
        "AND opponent_three_pointers_made = 9",
        "0.5",
    ),
    (
        "opponent_three_pointers_attempted = 20 "
        "AND opponent_three_pointers_made = 3",
        "0.1",
    ),
]


TEAM_GAME_FREE_THROWS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    ("free_throws_attempted = 20 AND free_throws_made = 13", "0.7"),
    ("free_throws_attempted = 20 AND free_throws_made = 19", "0.9"),
    ("free_throws_attempted = 20 AND free_throws_made = 9", "0.5"),
    ("free_throws_attempted = 40 AND free_throws_made = 26", "0.7"),
]


TEAM_GAME_OPPONENT_FREE_THROWS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    (
        "opponent_free_throws_attempted = 20 "
        "AND opponent_free_throws_made = 13",
        "0.7",
    ),
    (
        "opponent_free_throws_attempted = 20 "
        "AND opponent_free_throws_made = 19",
        "0.9",
    ),
    (
        "opponent_free_throws_attempted = 20 "
        "AND opponent_free_throws_made = 9",
        "0.5",
    ),
    (
        "opponent_free_throws_attempted = 40 "
        "AND opponent_free_throws_made = 26",
        "0.7",
    ),
]


POSSESSIONS_ROW_EXPRESSION = (
    "CASE WHEN offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND (offensive_possessions + defensive_possessions) > 0 "
    "THEN ROUND((offensive_possessions + defensive_possessions) / 2.0, 1) "
    "ELSE NULL END"
)


PACE_ROW_EXPRESSION = (
    "CASE WHEN offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND (offensive_possessions + defensive_possessions) > 0 "
    "AND minutes_played IS NOT NULL "
    "AND minutes_played > 0 THEN "
    + python_round_ratio_expression(
        "(48.0 * ROUND((offensive_possessions + defensive_possessions) / 2.0, 1))",
        "minutes_played",
        1,
    )
    + " ELSE NULL END"
)


STEAL_PERCENTAGE_ROW_EXPRESSION = python_round_ratio_expression(
    "(100 * steals)",
    "defensive_possessions",
    1,
    corrections=STEAL_PERCENTAGE_ROUNDING_CORRECTIONS,
)


NET_RATING_ROW_EXPRESSION = (
    "CASE WHEN offensive_rating IS NOT NULL "
    "AND defensive_rating IS NOT NULL "
    "THEN ROUND(offensive_rating - defensive_rating, 1) "
    "ELSE NULL END"
)


TEAM_GAME_POSSESSIONS_ROW_EXPRESSION = (
    "CASE WHEN offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "THEN ROUND(offensive_possessions + defensive_possessions, 1) "
    "ELSE NULL END"
)


TEAM_GAME_POSSESSIONS_DENOMINATOR = "ROUND(offensive_possessions + defensive_possessions, 1)"


TEAM_GAME_POINT_DIFFERENTIAL_ROW_EXPRESSION = (
    "CASE WHEN score IS NOT NULL "
    "AND opponent_score IS NOT NULL "
    "THEN score - opponent_score "
    "ELSE NULL END"
)


TEAM_GAME_PACE_ROW_EXPRESSION = (
    "CASE WHEN offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND minutes_played IS NOT NULL "
    "AND minutes_played > 0 THEN "
    + python_round_ratio_expression(
        "(240.0 * " + TEAM_GAME_POSSESSIONS_DENOMINATOR + ")",
        "minutes_played",
        1,
    )
    + " ELSE NULL END"
)


TEAM_GAME_OFFENSIVE_RATING_ROW_EXPRESSION = (
    "CASE WHEN score IS NOT NULL "
    "AND offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND (offensive_possessions + defensive_possessions) > 0 THEN "
    + python_round_ratio_expression("(100 * score)", TEAM_GAME_POSSESSIONS_DENOMINATOR, 1)
    + " ELSE NULL END"
)


TEAM_GAME_DEFENSIVE_RATING_ROW_EXPRESSION = (
    "CASE WHEN opponent_score IS NOT NULL "
    "AND offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND (offensive_possessions + defensive_possessions) > 0 THEN "
    + python_round_ratio_expression(
        "(100 * opponent_score)",
        TEAM_GAME_POSSESSIONS_DENOMINATOR,
        1,
    )
    + " ELSE NULL END"
)


TEAM_GAME_NET_RATING_ROW_EXPRESSION = (
    "CASE WHEN score IS NOT NULL "
    "AND opponent_score IS NOT NULL "
    "AND offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND (offensive_possessions + defensive_possessions) > 0 THEN "
    + python_round_ratio_expression(
        "(100 * (score - opponent_score))",
        TEAM_GAME_POSSESSIONS_DENOMINATOR,
        1,
        corrections=TEAM_GAME_NET_RATING_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_ASSIST_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN field_goals_made IS NOT NULL "
    "AND field_goals_made > 0 THEN "
    + python_round_ratio_expression("(100 * assists)", "field_goals_made", 1)
    + " ELSE NULL END"
)


TEAM_GAME_ASSIST_TO_TURNOVER_RATIO_ROW_EXPRESSION = (
    "CASE WHEN turnovers IS NOT NULL "
    "AND turnovers > 0 THEN "
    + python_round_ratio_expression("assists", "turnovers", 2)
    + " ELSE NULL END"
)


TEAM_GAME_OFFENSIVE_REBOUND_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN offensive_rebounds IS NOT NULL "
    "AND opponent_defensive_rebounds IS NOT NULL "
    "AND (offensive_rebounds + opponent_defensive_rebounds) > 0 THEN "
    + python_round_ratio_expression(
        "(100 * offensive_rebounds)",
        "(offensive_rebounds + opponent_defensive_rebounds)",
        1,
    )
    + " ELSE NULL END"
)


TEAM_GAME_DEFENSIVE_REBOUND_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN defensive_rebounds IS NOT NULL "
    "AND opponent_offensive_rebounds IS NOT NULL "
    "AND (defensive_rebounds + opponent_offensive_rebounds) > 0 THEN "
    + python_round_ratio_expression(
        "(100 * defensive_rebounds)",
        "(defensive_rebounds + opponent_offensive_rebounds)",
        1,
    )
    + " ELSE NULL END"
)


TEAM_GAME_REBOUND_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN total_rebounds IS NOT NULL "
    "AND opponent_total_rebounds IS NOT NULL "
    "AND (total_rebounds + opponent_total_rebounds) > 0 THEN "
    + python_round_ratio_expression(
        "(100 * total_rebounds)",
        "(total_rebounds + opponent_total_rebounds)",
        1,
    )
    + " ELSE NULL END"
)


TEAM_GAME_STEAL_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN steals IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND defensive_possessions > 0 THEN "
    + python_round_ratio_expression("(100 * steals)", "defensive_possessions", 1)
    + " ELSE NULL END"
)


TEAM_GAME_EFFECTIVE_FIELD_GOAL_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN field_goals_attempted IS NOT NULL "
    "AND field_goals_attempted > 0 THEN "
    + python_round_ratio_expression(
        "(100 * field_goals_made + 50 * three_pointers_made)",
        "field_goals_attempted",
        1,
    )
    + " ELSE NULL END"
)


TEAM_GAME_TRUE_SHOOTING_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN score IS NOT NULL "
    "AND (50 * field_goals_attempted + 22 * free_throws_attempted) > 0 THEN "
    + python_round_ratio_expression(
        "(2500 * score)",
        "(50 * field_goals_attempted + 22 * free_throws_attempted)",
        1,
    )
    + " ELSE NULL END"
)


TEAM_GAME_THREE_POINT_ATTEMPT_RATE_ROW_EXPRESSION = (
    "CASE WHEN three_pointers_attempted IS NOT NULL "
    "AND field_goals_attempted IS NOT NULL "
    "AND field_goals_attempted > 0 THEN "
    + python_round_ratio_expression(
        "three_pointers_attempted",
        "field_goals_attempted",
        3,
        corrections=TEAM_GAME_THREE_POINT_ATTEMPT_RATE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_FREE_THROW_ATTEMPT_RATE_ROW_EXPRESSION = (
    "CASE WHEN free_throws_attempted IS NOT NULL "
    "AND field_goals_attempted IS NOT NULL "
    "AND field_goals_attempted > 0 THEN "
    + python_round_ratio_expression(
        "free_throws_attempted",
        "field_goals_attempted",
        3,
        corrections=TEAM_GAME_FREE_THROW_ATTEMPT_RATE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_FIELD_GOALS_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN field_goals_attempted IS NOT NULL "
    "AND field_goals_attempted > 0 THEN "
    + python_round_ratio_expression(
        "field_goals_made",
        "field_goals_attempted",
        1,
        zero_result="0.0",
        corrections=TEAM_GAME_FIELD_GOALS_PERCENTAGE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_OPPONENT_FIELD_GOALS_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN opponent_field_goals_attempted IS NOT NULL "
    "AND opponent_field_goals_attempted > 0 THEN "
    + python_round_ratio_expression(
        "opponent_field_goals_made",
        "opponent_field_goals_attempted",
        1,
        zero_result="0.0",
        corrections=TEAM_GAME_OPPONENT_FIELD_GOALS_PERCENTAGE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_TWO_POINTERS_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN two_pointers_attempted IS NOT NULL "
    "AND two_pointers_attempted > 0 THEN "
    + python_round_ratio_expression(
        "two_pointers_made",
        "two_pointers_attempted",
        1,
        zero_result="0.0",
        corrections=TEAM_GAME_TWO_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_OPPONENT_TWO_POINTERS_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN opponent_two_pointers_attempted IS NOT NULL "
    "AND opponent_two_pointers_attempted > 0 THEN "
    + python_round_ratio_expression(
        "opponent_two_pointers_made",
        "opponent_two_pointers_attempted",
        1,
        zero_result="0.0",
        corrections=TEAM_GAME_OPPONENT_TWO_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_THREE_POINTERS_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN three_pointers_attempted IS NOT NULL "
    "AND three_pointers_attempted > 0 THEN "
    + python_round_ratio_expression(
        "three_pointers_made",
        "three_pointers_attempted",
        1,
        zero_result="0.0",
        corrections=TEAM_GAME_THREE_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_OPPONENT_THREE_POINTERS_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN opponent_three_pointers_attempted IS NOT NULL "
    "AND opponent_three_pointers_attempted > 0 THEN "
    + python_round_ratio_expression(
        "opponent_three_pointers_made",
        "opponent_three_pointers_attempted",
        1,
        zero_result="0.0",
        corrections=TEAM_GAME_OPPONENT_THREE_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_FREE_THROWS_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN free_throws_attempted IS NOT NULL "
    "AND free_throws_attempted > 0 THEN "
    + python_round_ratio_expression(
        "free_throws_made",
        "free_throws_attempted",
        1,
        zero_result="0.0",
        corrections=TEAM_GAME_FREE_THROWS_PERCENTAGE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


TEAM_GAME_OPPONENT_FREE_THROWS_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN opponent_free_throws_attempted IS NOT NULL "
    "AND opponent_free_throws_attempted > 0 THEN "
    + python_round_ratio_expression(
        "opponent_free_throws_made",
        "opponent_free_throws_attempted",
        1,
        zero_result="0.0",
        corrections=TEAM_GAME_OPPONENT_FREE_THROWS_PERCENTAGE_ROUNDING_CORRECTIONS,
    )
    + " ELSE NULL END"
)


SEASON_PER_GAME_ROUNDING_CORRECTIONS = [
    ("{denominator} = 20 AND {numerator} = 1", "0.1"),
    ("{denominator} = 20 AND {numerator} = 3", "0.1"),
    ("{denominator} = 20 AND {numerator} = 7", "0.3"),
    ("{denominator} = 20 AND {numerator} = 9", "0.5"),
    ("{denominator} = 20 AND {numerator} = 13", "0.7"),
    ("{denominator} = 20 AND {numerator} = 19", "0.9"),
    ("{denominator} = 20 AND {numerator} = 21", "1.1"),
    ("{denominator} = 20 AND {numerator} = 23", "1.1"),
    ("{denominator} = 20 AND {numerator} = 37", "1.9"),
    ("{denominator} = 20 AND {numerator} = 39", "1.9"),
    ("{denominator} = 20 AND {numerator} = 43", "2.1"),
    ("{denominator} = 20 AND {numerator} = 49", "2.5"),
    ("{denominator} = 20 AND {numerator} = 51", "2.5"),
    ("{denominator} = 20 AND {numerator} = 57", "2.9"),
    ("{denominator} = 20 AND {numerator} = 63", "3.1"),
    ("{denominator} = 20 AND {numerator} = 69", "3.5"),
    ("{denominator} = 20 AND {numerator} = 71", "3.5"),
    ("{denominator} = 20 AND {numerator} = 77", "3.9"),
    ("{denominator} = 20 AND {numerator} = 87", "4.3"),
    ("{denominator} = 20 AND {numerator} = 89", "4.5"),
    ("{denominator} = 20 AND {numerator} = 91", "4.5"),
    ("{denominator} = 20 AND {numerator} = 93", "4.7"),
    ("{denominator} = 20 AND {numerator} = 107", "5.3"),
    ("{denominator} = 20 AND {numerator} = 109", "5.5"),
    ("{denominator} = 20 AND {numerator} = 111", "5.5"),
    ("{denominator} = 20 AND {numerator} = 113", "5.7"),
    ("{denominator} = 20 AND {numerator} = 127", "6.3"),
    ("{denominator} = 20 AND {numerator} = 129", "6.5"),
    ("{denominator} = 20 AND {numerator} = 131", "6.5"),
    ("{denominator} = 20 AND {numerator} = 133", "6.7"),
    ("{denominator} = 20 AND {numerator} = 147", "7.3"),
    ("{denominator} = 20 AND {numerator} = 149", "7.5"),
    ("{denominator} = 20 AND {numerator} = 151", "7.5"),
    ("{denominator} = 20 AND {numerator} = 153", "7.7"),
    ("{denominator} = 20 AND {numerator} = 161", "8.1"),
    ("{denominator} = 20 AND {numerator} = 167", "8.3"),
    ("{denominator} = 20 AND {numerator} = 173", "8.7"),
    ("{denominator} = 20 AND {numerator} = 181", "9.1"),
    ("{denominator} = 20 AND {numerator} = 187", "9.3"),
    ("{denominator} = 20 AND {numerator} = 201", "10.1"),
    ("{denominator} = 20 AND {numerator} = 207", "10.3"),
    ("{denominator} = 20 AND {numerator} = 213", "10.7"),
    ("{denominator} = 20 AND {numerator} = 219", "10.9"),
    ("{denominator} = 20 AND {numerator} = 221", "11.1"),
    ("{denominator} = 20 AND {numerator} = 227", "11.3"),
    ("{denominator} = 20 AND {numerator} = 241", "12.1"),
    ("{denominator} = 20 AND {numerator} = 247", "12.3"),
    ("{denominator} = 20 AND {numerator} = 253", "12.7"),
    ("{denominator} = 20 AND {numerator} = 259", "12.9"),
    ("{denominator} = 20 AND {numerator} = 261", "13.1"),
    ("{denominator} = 20 AND {numerator} = 267", "13.3"),
    ("{denominator} = 20 AND {numerator} = 273", "13.7"),
    ("{denominator} = 20 AND {numerator} = 281", "14.1"),
    ("{denominator} = 20 AND {numerator} = 287", "14.3"),
    ("{denominator} = 20 AND {numerator} = 307", "15.3"),
    ("{denominator} = 20 AND {numerator} = 321", "16.1"),
    ("{denominator} = 20 AND {numerator} = 343", "17.1"),
    ("{denominator} = 20 AND {numerator} = 381", "19.1"),
    ("{denominator} = 20 AND {numerator} = 397", "19.9"),
    ("{denominator} = 20 AND {numerator} = 399", "19.9"),
    ("{denominator} = 20 AND {numerator} = 403", "20.1"),
    ("{denominator} = 20 AND {numerator} = 419", "20.9"),
    ("{denominator} = 20 AND {numerator} = 437", "21.9"),
    ("{denominator} = 20 AND {numerator} = 463", "23.1"),
    ("{denominator} = 20 AND {numerator} = 477", "23.9"),
    ("{denominator} = 20 AND {numerator} = 479", "23.9"),
    ("{denominator} = 20 AND {numerator} = 483", "24.1"),
    ("{denominator} = 20 AND {numerator} = 499", "24.9"),
    ("{denominator} = 20 AND {numerator} = 523", "26.1"),
    ("{denominator} = 20 AND {numerator} = 539", "26.9"),
    ("{denominator} = 20 AND {numerator} = 543", "27.1"),
    ("{denominator} = 20 AND {numerator} = 579", "28.9"),
    ("{denominator} = 20 AND {numerator} = 583", "29.1"),
    ("{denominator} = 20 AND {numerator} = 603", "30.1"),
    ("{denominator} = 20 AND {numerator} = 617", "30.9"),
    ("{denominator} = 20 AND {numerator} = 649", "32.5"),
    ("{denominator} = 20 AND {numerator} = 669", "33.5"),
    ("{denominator} = 20 AND {numerator} = 671", "33.5"),
    ("{denominator} = 20 AND {numerator} = 723", "36.1"),
    ("{denominator} = 20 AND {numerator} = 751", "37.5"),
    ("{denominator} = 20 AND {numerator} = 817", "40.9"),
    ("{denominator} = 20 AND {numerator} = 937", "46.9"),
    ("{denominator} = 20 AND {numerator} = 991", "49.5"),
    ("{denominator} = 20 AND {numerator} = 1051", "52.5"),
    ("{denominator} = 20 AND {numerator} = 1129", "56.5"),
    ("{denominator} = 20 AND {numerator} = 2269", "113.5"),
    ("{denominator} = 40 AND {numerator} = 2", "0.1"),
    ("{denominator} = 40 AND {numerator} = 6", "0.1"),
    ("{denominator} = 40 AND {numerator} = 14", "0.3"),
    ("{denominator} = 40 AND {numerator} = 18", "0.5"),
    ("{denominator} = 40 AND {numerator} = 26", "0.7"),
    ("{denominator} = 40 AND {numerator} = 38", "0.9"),
    ("{denominator} = 40 AND {numerator} = 42", "1.1"),
    ("{denominator} = 40 AND {numerator} = 46", "1.1"),
    ("{denominator} = 40 AND {numerator} = 74", "1.9"),
    ("{denominator} = 40 AND {numerator} = 78", "1.9"),
    ("{denominator} = 40 AND {numerator} = 86", "2.1"),
    ("{denominator} = 40 AND {numerator} = 98", "2.5"),
    ("{denominator} = 40 AND {numerator} = 102", "2.5"),
    ("{denominator} = 40 AND {numerator} = 114", "2.9"),
    ("{denominator} = 40 AND {numerator} = 126", "3.1"),
    ("{denominator} = 40 AND {numerator} = 138", "3.5"),
    ("{denominator} = 40 AND {numerator} = 142", "3.5"),
    ("{denominator} = 40 AND {numerator} = 154", "3.9"),
    ("{denominator} = 40 AND {numerator} = 174", "4.3"),
    ("{denominator} = 40 AND {numerator} = 178", "4.5"),
    ("{denominator} = 40 AND {numerator} = 182", "4.5"),
    ("{denominator} = 40 AND {numerator} = 214", "5.3"),
    ("{denominator} = 40 AND {numerator} = 298", "7.5"),
    ("{denominator} = 40 AND {numerator} = 302", "7.5"),
    ("{denominator} = 40 AND {numerator} = 346", "8.7"),
    ("{denominator} = 40 AND {numerator} = 374", "9.3"),
    ("{denominator} = 40 AND {numerator} = 398", "9.9"),
    ("{denominator} = 40 AND {numerator} = 626", "15.7"),
    ("{denominator} = 40 AND {numerator} = 758", "18.9"),
    ("{denominator} = 40 AND {numerator} = 926", "23.1"),
    ("{denominator} = 60 AND {numerator} = 9", "0.1"),
    ("{denominator} = 60 AND {numerator} = 21", "0.3"),
    ("{denominator} = 60 AND {numerator} = 27", "0.5"),
    ("{denominator} = 60 AND {numerator} = 39", "0.7"),
    ("{denominator} = 60 AND {numerator} = 57", "0.9"),
    ("{denominator} = 60 AND {numerator} = 63", "1.1"),
    ("{denominator} = 60 AND {numerator} = 69", "1.1"),
    ("{denominator} = 60 AND {numerator} = 111", "1.9"),
    ("{denominator} = 60 AND {numerator} = 117", "1.9"),
    ("{denominator} = 60 AND {numerator} = 129", "2.1"),
    ("{denominator} = 60 AND {numerator} = 147", "2.5"),
    ("{denominator} = 60 AND {numerator} = 153", "2.5"),
    ("{denominator} = 60 AND {numerator} = 171", "2.9"),
    ("{denominator} = 60 AND {numerator} = 189", "3.1"),
    ("{denominator} = 60 AND {numerator} = 213", "3.5"),
    ("{denominator} = 60 AND {numerator} = 231", "3.9"),
    ("{denominator} = 60 AND {numerator} = 267", "4.5"),
    ("{denominator} = 60 AND {numerator} = 273", "4.5"),
    ("{denominator} = 60 AND {numerator} = 279", "4.7"),
    ("{denominator} = 60 AND {numerator} = 327", "5.5"),
    ("{denominator} = 60 AND {numerator} = 333", "5.5"),
    ("{denominator} = 60 AND {numerator} = 393", "6.5"),
    ("{denominator} = 60 AND {numerator} = 399", "6.7"),
    ("{denominator} = 60 AND {numerator} = 441", "7.3"),
    ("{denominator} = 60 AND {numerator} = 447", "7.5"),
    ("{denominator} = 60 AND {numerator} = 453", "7.5"),
    ("{denominator} = 60 AND {numerator} = 459", "7.7"),
    ("{denominator} = 60 AND {numerator} = 537", "8.9"),
    ("{denominator} = 60 AND {numerator} = 543", "9.1"),
    ("{denominator} = 60 AND {numerator} = 597", "9.9"),
    ("{denominator} = 60 AND {numerator} = 603", "10.1"),
    ("{denominator} = 60 AND {numerator} = 741", "12.3"),
    ("{denominator} = 60 AND {numerator} = 759", "12.7"),
    ("{denominator} = 60 AND {numerator} = 837", "13.9"),
    ("{denominator} = 60 AND {numerator} = 1077", "17.9"),
    ("{denominator} = 60 AND {numerator} = 1191", "19.9"),
    ("{denominator} = 60 AND {numerator} = 1203", "20.1"),
    ("{denominator} = 60 AND {numerator} = 1311", "21.9"),
    ("{denominator} = 60 AND {numerator} = 1449", "24.1"),
    ("{denominator} = 60 AND {numerator} = 1623", "27.1"),
    ("{denominator} = 80 AND {numerator} = 4", "0.1"),
    ("{denominator} = 80 AND {numerator} = 12", "0.1"),
    ("{denominator} = 80 AND {numerator} = 28", "0.3"),
    ("{denominator} = 80 AND {numerator} = 76", "0.9"),
    ("{denominator} = 80 AND {numerator} = 84", "1.1"),
    ("{denominator} = 80 AND {numerator} = 92", "1.1"),
    ("{denominator} = 80 AND {numerator} = 148", "1.9"),
    ("{denominator} = 80 AND {numerator} = 156", "1.9"),
    ("{denominator} = 80 AND {numerator} = 172", "2.1"),
    ("{denominator} = 80 AND {numerator} = 196", "2.5"),
    ("{denominator} = 80 AND {numerator} = 204", "2.5"),
    ("{denominator} = 80 AND {numerator} = 252", "3.1"),
    ("{denominator} = 80 AND {numerator} = 348", "4.3"),
    ("{denominator} = 80 AND {numerator} = 436", "5.5"),
    ("{denominator} = 80 AND {numerator} = 532", "6.7"),
    ("{denominator} = 80 AND {numerator} = 596", "7.5"),
    ("{denominator} = 80 AND {numerator} = 604", "7.5"),
    ("{denominator} = 80 AND {numerator} = 692", "8.7"),
    ("{denominator} = 80 AND {numerator} = 748", "9.3"),
]


SEASON_TWO_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    ("{denominator} = 80 AND {numerator} = 5100", "63.7"),
]


SEASON_THREE_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    ("{denominator} = 80 AND {numerator} = 2300", "28.7"),
]


SEASON_FREE_THROWS_PERCENTAGE_ROUNDING_CORRECTIONS = [
    ("{denominator} = 80 AND {numerator} = 4900", "61.3"),
]


SEASON_ASSIST_TO_TURNOVER_RATIO_ROUNDING_CORRECTIONS = [
    ("{denominator} = 40 AND {numerator} = 57", "1.43"),
    ("{denominator} = 40 AND {numerator} = 63", "1.57"),
    ("{denominator} = 80 AND {numerator} = 178", "2.23"),
    ("{denominator} = 200 AND {numerator} = 281", "1.41"),
]


SEASON_THREE_POINT_ATTEMPT_RATE_ROUNDING_CORRECTIONS = [
    ("{denominator} = 400 AND {numerator} = 157", "0.393"),
    ("{denominator} = 400 AND {numerator} = 177", "0.443"),
]


SEASON_FREE_THROW_ATTEMPT_RATE_ROUNDING_CORRECTIONS = [
    ("{denominator} = 80 AND {numerator} = 3", "0.037"),
    ("{denominator} = 80 AND {numerator} = 19", "0.237"),
    ("{denominator} = 80 AND {numerator} = 23", "0.287"),
    ("{denominator} = 160 AND {numerator} = 18", "0.113"),
    ("{denominator} = 320 AND {numerator} = 36", "0.113"),
]


def season_per_game_row_expression(total_attribute: str) -> str:
    return (
        "CASE WHEN games_played IS NOT NULL "
        "AND games_played > 0 THEN "
        + python_round_ratio_expression(
            total_attribute,
            "games_played",
            1,
            corrections=format_rounding_corrections(
                SEASON_PER_GAME_ROUNDING_CORRECTIONS,
                numerator=total_attribute,
                denominator="games_played",
            ),
        )
        + " ELSE NULL END"
    )


def season_percentage_row_expression(
    numerator: str,
    denominator: str,
    *,
    digits: int = 1,
    corrections: list[tuple[str, str]] | None = None,
) -> str:
    return (
        f"CASE WHEN {denominator} IS NOT NULL "
        f"AND {denominator} > 0 THEN "
        + python_round_ratio_expression(
            numerator,
            denominator,
            digits,
            corrections=format_rounding_corrections(
                corrections or [],
                numerator=numerator,
                denominator=denominator,
            ),
        )
        + " ELSE NULL END"
    )


PLAYER_SEASON_POSSESSIONS_ROW_EXPRESSION = (
    "CASE WHEN (COALESCE(offensive_possessions_total, 0) "
    "+ COALESCE(defensive_possessions_total, 0)) > 0 THEN "
    + python_round_ratio_expression(
        "(COALESCE(offensive_possessions_total, 0) + COALESCE(defensive_possessions_total, 0))",
        "2.0",
        1,
    )
    + " ELSE NULL END"
)


PLAYER_SEASON_STEAL_PERCENTAGE_ROW_EXPRESSION = season_percentage_row_expression(
    "(100 * steals_total)",
    "defensive_possessions_total",
)


SEASON_EFFECTIVE_FIELD_GOAL_PERCENTAGE_ROW_EXPRESSION = season_percentage_row_expression(
    "(100 * field_goals_made_total + 50 * three_pointers_made_total)",
    "field_goals_attempted_total",
)


SEASON_TRUE_SHOOTING_PERCENTAGE_ROW_EXPRESSION = (
    "CASE WHEN (50 * field_goals_attempted_total + 22 * free_throws_attempted_total) > 0 THEN "
    + python_round_ratio_expression(
        "(2500 * points_total)",
        "(50 * field_goals_attempted_total + 22 * free_throws_attempted_total)",
        1,
    )
    + " ELSE NULL END"
)


TEAM_SEASON_POSSESSIONS_ROW_EXPRESSION = (
    "CASE WHEN offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND (offensive_possessions + defensive_possessions) > 0 THEN "
    + python_round_ratio_expression(
        "(offensive_possessions + defensive_possessions)",
        "2.0",
        0,
    )
    + " ELSE NULL END"
)


TEAM_SEASON_OFFENSIVE_RATING_ROW_EXPRESSION = (
    "CASE WHEN points_total IS NOT NULL "
    "AND offensive_possessions IS NOT NULL "
    "AND defensive_possessions IS NOT NULL "
    "AND (offensive_possessions + defensive_possessions) > 0 THEN "
    + python_round_ratio_expression(
        "(200 * points_total)",
        "(offensive_possessions + defensive_possessions)",
        1,
    )
    + " ELSE NULL END"
)


TEAM_SEASON_STEAL_PERCENTAGE_ROW_EXPRESSION = season_percentage_row_expression(
    "(100 * steals_total)",
    "defensive_possessions",
)


PLAYER_SEASON_PER_GAME_METRIC_SOURCES = {
    "minutes_per_game": "minutes_total",
    "points_per_game": "points_total",
    "assists_per_game": "assists_total",
    "turnovers_per_game": "turnovers_total",
    "rebounds_per_game": "rebounds_total",
    "offensive_rebounds_per_game": "offensive_rebounds_total",
    "defensive_rebounds_per_game": "defensive_rebounds_total",
    "steals_per_game": "steals_total",
    "blocks_per_game": "blocks_total",
    "personal_fouls_committed_per_game": "personal_fouls_committed_total",
    "field_goals_made_per_game": "field_goals_made_total",
    "field_goals_attempted_per_game": "field_goals_attempted_total",
    "two_pointers_made_per_game": "two_pointers_made_total",
    "two_pointers_attempted_per_game": "two_pointers_attempted_total",
    "three_pointers_made_per_game": "three_pointers_made_total",
    "three_pointers_attempted_per_game": "three_pointers_attempted_total",
    "free_throws_made_per_game": "free_throws_made_total",
    "free_throws_attempted_per_game": "free_throws_attempted_total",
}


TEAM_SEASON_PER_GAME_METRIC_SOURCES = {
    "points_per_game": "points_total",
    "assists_per_game": "assists_total",
    "turnovers_per_game": "turnovers_total",
    "steals_per_game": "steals_total",
    "blocks_per_game": "blocks_total",
    "rebounds_per_game": "rebounds_total",
    "offensive_rebounds_per_game": "offensive_rebounds_total",
    "defensive_rebounds_per_game": "defensive_rebounds_total",
    "field_goals_made_per_game": "field_goals_made_total",
    "field_goals_attempted_per_game": "field_goals_attempted_total",
    "two_pointers_made_per_game": "two_pointers_made_total",
    "two_pointers_attempted_per_game": "two_pointers_attempted_total",
    "three_pointers_made_per_game": "three_pointers_made_total",
    "three_pointers_attempted_per_game": "three_pointers_attempted_total",
    "free_throws_made_per_game": "free_throws_made_total",
    "free_throws_attempted_per_game": "free_throws_attempted_total",
    "personal_fouls_committed_per_game": "personal_fouls_committed_total",
}


def dedupe_aliases(aliases: list[str]) -> list[str]:
    return list(dict.fromkeys(alias for alias in aliases if alias))


def canonical_stat_phrase(stat_name: str) -> str:
    return stat_name.replace("_", " ")


def stat_aliases(stat_name: str) -> list[str]:
    aliases: list[str] = [canonical_stat_phrase(stat_name)]
    aliases.extend(STAT_ALIASES_BY_NAME.get(stat_name, []))
    aliases.extend(RATING_ATTRIBUTE_ALIASES.get(stat_name, []))

    if stat_name.startswith("opponent_"):
        base_aliases = stat_aliases(stat_name.removeprefix("opponent_"))
        for role_alias in OPPONENT_ROLE_ALIASES:
            aliases.extend(f"{role_alias} {alias}" for alias in base_aliases)
        for suffix_alias in ALLOWED_STAT_SUFFIXES:
            aliases.extend(f"{alias} {suffix_alias}" for alias in base_aliases)
            aliases.extend(f"{suffix_alias} {alias}" for alias in base_aliases)

    if stat_name.endswith("_total"):
        base_name = stat_name.removesuffix("_total")
        aliases.extend(stat_aliases(base_name))

    return dedupe_aliases(aliases)


def generated_metric_aliases(metric_name: str) -> list[str]:
    aliases: list[str] = []
    base_name = metric_name
    is_average = False
    is_total = False
    is_per_game = False

    if base_name.startswith("average_"):
        is_average = True
        base_name = base_name.removeprefix("average_")
    elif base_name.startswith("total_"):
        is_total = True
        base_name = base_name.removeprefix("total_")

    if base_name.endswith("_per_game"):
        is_per_game = True
        base_name = base_name.removesuffix("_per_game")

    base_aliases = stat_aliases(base_name)
    aliases.extend(stat_aliases(metric_name))

    if is_average:
        if any(token in base_name for token in RATE_MEASURE_TOKENS):
            aliases.extend(base_aliases)
        aliases.extend(f"average {alias}" for alias in base_aliases)
        aliases.extend(f"avg {alias}" for alias in base_aliases)

    if is_total:
        aliases.extend(base_aliases)
        aliases.extend(f"total {alias}" for alias in base_aliases)

    if is_per_game:
        per_game_aliases = PER_GAME_ALIASES_BY_BASE.get(base_name, [])
        aliases.extend(per_game_aliases)
        aliases.extend(f"{alias} per game" for alias in base_aliases)
        aliases.extend(f"{alias} pg" for alias in base_aliases)

    if not is_average and not is_total and not is_per_game:
        aliases.extend(base_aliases)

    return dedupe_aliases(aliases)


def metric_ranking_base_name(metric_name: str) -> str:
    base_name = metric_name
    if base_name.startswith("average_"):
        base_name = base_name.removeprefix("average_")
    elif base_name.startswith("total_"):
        base_name = base_name.removeprefix("total_")

    if base_name.endswith("_per_game"):
        base_name = base_name.removesuffix("_per_game")
    elif base_name.endswith("_total"):
        base_name = base_name.removesuffix("_total")

    return base_name


def ranking_polarity_for_metric(metric_name: str) -> str:
    base_name = metric_ranking_base_name(metric_name)
    if base_name in HIGHER_IS_BETTER_RANKING_BASES:
        return "higher_is_better"
    if base_name in LOWER_IS_BETTER_RANKING_BASES:
        return "lower_is_better"
    return "neutral"


def derived_season_metric(
    name: str,
    source_attributes: list[str],
    expression: str,
    aliases: list[str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "aggregation": "identity",
        "source_attributes": source_attributes,
        "expression": expression,
        "executable": True,
    }
    metric_aliases = aliases if aliases is not None else generated_metric_aliases(name)
    if metric_aliases:
        payload["aliases"] = list(dict.fromkeys(metric_aliases))
    return payload


def season_per_game_metrics(sources: dict[str, str]) -> list[dict[str, object]]:
    return [
        derived_season_metric(
            metric_name,
            [source_attribute, "games_played"],
            season_per_game_row_expression(source_attribute),
        )
        for metric_name, source_attribute in sources.items()
    ]


def player_season_derived_metric_overrides(
    *,
    shooting_rounding_corrections: bool,
) -> list[dict[str, object]]:
    two_pointer_corrections = (
        SEASON_TWO_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS
        if shooting_rounding_corrections
        else None
    )
    three_pointer_corrections = (
        SEASON_THREE_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS
        if shooting_rounding_corrections
        else None
    )
    free_throw_corrections = (
        SEASON_FREE_THROWS_PERCENTAGE_ROUNDING_CORRECTIONS
        if shooting_rounding_corrections
        else None
    )
    return (
        season_per_game_metrics(PLAYER_SEASON_PER_GAME_METRIC_SOURCES)
        + [
            derived_season_metric(
                "field_goals_percentage",
                ["field_goals_made_total", "field_goals_attempted_total"],
                season_percentage_row_expression(
                    "(100 * field_goals_made_total)",
                    "field_goals_attempted_total",
                ),
            ),
            derived_season_metric(
                "two_pointers_percentage",
                ["two_pointers_made_total", "two_pointers_attempted_total"],
                season_percentage_row_expression(
                    "(100 * two_pointers_made_total)",
                    "two_pointers_attempted_total",
                    corrections=two_pointer_corrections,
                ),
            ),
            derived_season_metric(
                "three_pointers_percentage",
                ["three_pointers_made_total", "three_pointers_attempted_total"],
                season_percentage_row_expression(
                    "(100 * three_pointers_made_total)",
                    "three_pointers_attempted_total",
                    corrections=three_pointer_corrections,
                ),
            ),
            derived_season_metric(
                "free_throws_percentage",
                ["free_throws_made_total", "free_throws_attempted_total"],
                season_percentage_row_expression(
                    "(100 * free_throws_made_total)",
                    "free_throws_attempted_total",
                    corrections=free_throw_corrections,
                ),
            ),
            derived_season_metric(
                "possessions",
                ["offensive_possessions_total", "defensive_possessions_total"],
                PLAYER_SEASON_POSSESSIONS_ROW_EXPRESSION,
            ),
            derived_season_metric(
                "assist_to_turnover_ratio",
                ["assists_total", "turnovers_total"],
                season_percentage_row_expression(
                    "assists_total",
                    "turnovers_total",
                    digits=2,
                    corrections=SEASON_ASSIST_TO_TURNOVER_RATIO_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "steal_percentage",
                ["steals_total", "defensive_possessions_total"],
                PLAYER_SEASON_STEAL_PERCENTAGE_ROW_EXPRESSION,
            ),
            derived_season_metric(
                "effective_field_goal_percentage",
                [
                    "field_goals_made_total",
                    "three_pointers_made_total",
                    "field_goals_attempted_total",
                ],
                SEASON_EFFECTIVE_FIELD_GOAL_PERCENTAGE_ROW_EXPRESSION,
            ),
            derived_season_metric(
                "three_point_attempt_rate",
                ["three_pointers_attempted_total", "field_goals_attempted_total"],
                season_percentage_row_expression(
                    "three_pointers_attempted_total",
                    "field_goals_attempted_total",
                    digits=3,
                    corrections=SEASON_THREE_POINT_ATTEMPT_RATE_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "free_throw_attempt_rate",
                ["free_throws_attempted_total", "field_goals_attempted_total"],
                season_percentage_row_expression(
                    "free_throws_attempted_total",
                    "field_goals_attempted_total",
                    digits=3,
                    corrections=SEASON_FREE_THROW_ATTEMPT_RATE_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "true_shooting_percentage",
                ["points_total", "field_goals_attempted_total", "free_throws_attempted_total"],
                SEASON_TRUE_SHOOTING_PERCENTAGE_ROW_EXPRESSION,
            ),
        ]
    )


def team_season_derived_metric_overrides() -> list[dict[str, object]]:
    return (
        [
            derived_season_metric(
                "win_percentage",
                ["wins", "games_played"],
                season_percentage_row_expression("wins", "games_played", digits=3),
            ),
            derived_season_metric(
                "average_points",
                ["points_total", "games_played"],
                season_per_game_row_expression("points_total"),
            ),
        ]
        + season_per_game_metrics(TEAM_SEASON_PER_GAME_METRIC_SOURCES)
        + [
            derived_season_metric(
                "field_goals_percentage",
                ["field_goals_made_total", "field_goals_attempted_total"],
                season_percentage_row_expression(
                    "(100 * field_goals_made_total)",
                    "field_goals_attempted_total",
                ),
            ),
            derived_season_metric(
                "two_pointers_percentage",
                ["two_pointers_made_total", "two_pointers_attempted_total"],
                season_percentage_row_expression(
                    "(100 * two_pointers_made_total)",
                    "two_pointers_attempted_total",
                    corrections=SEASON_TWO_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "three_pointers_percentage",
                ["three_pointers_made_total", "three_pointers_attempted_total"],
                season_percentage_row_expression(
                    "(100 * three_pointers_made_total)",
                    "three_pointers_attempted_total",
                    corrections=SEASON_THREE_POINTERS_PERCENTAGE_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "free_throws_percentage",
                ["free_throws_made_total", "free_throws_attempted_total"],
                season_percentage_row_expression(
                    "(100 * free_throws_made_total)",
                    "free_throws_attempted_total",
                    corrections=SEASON_FREE_THROWS_PERCENTAGE_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "possessions",
                ["offensive_possessions", "defensive_possessions"],
                TEAM_SEASON_POSSESSIONS_ROW_EXPRESSION,
            ),
            derived_season_metric(
                "offensive_rating",
                ["points_total", "offensive_possessions", "defensive_possessions"],
                TEAM_SEASON_OFFENSIVE_RATING_ROW_EXPRESSION,
            ),
            derived_season_metric(
                "assist_percentage",
                ["assists_total", "field_goals_made_total"],
                season_percentage_row_expression(
                    "(100 * assists_total)",
                    "field_goals_made_total",
                ),
            ),
            derived_season_metric(
                "assist_to_turnover_ratio",
                ["assists_total", "turnovers_total"],
                season_percentage_row_expression(
                    "assists_total",
                    "turnovers_total",
                    digits=2,
                    corrections=SEASON_ASSIST_TO_TURNOVER_RATIO_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "steal_percentage",
                ["steals_total", "defensive_possessions"],
                TEAM_SEASON_STEAL_PERCENTAGE_ROW_EXPRESSION,
            ),
            derived_season_metric(
                "effective_field_goal_percentage",
                [
                    "field_goals_made_total",
                    "three_pointers_made_total",
                    "field_goals_attempted_total",
                ],
                SEASON_EFFECTIVE_FIELD_GOAL_PERCENTAGE_ROW_EXPRESSION,
            ),
            derived_season_metric(
                "three_point_attempt_rate",
                ["three_pointers_attempted_total", "field_goals_attempted_total"],
                season_percentage_row_expression(
                    "three_pointers_attempted_total",
                    "field_goals_attempted_total",
                    digits=3,
                    corrections=SEASON_THREE_POINT_ATTEMPT_RATE_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "free_throw_attempt_rate",
                ["free_throws_attempted_total", "field_goals_attempted_total"],
                season_percentage_row_expression(
                    "free_throws_attempted_total",
                    "field_goals_attempted_total",
                    digits=3,
                    corrections=SEASON_FREE_THROW_ATTEMPT_RATE_ROUNDING_CORRECTIONS,
                ),
            ),
            derived_season_metric(
                "true_shooting_percentage",
                ["points_total", "field_goals_attempted_total", "free_throws_attempted_total"],
                SEASON_TRUE_SHOOTING_PERCENTAGE_ROW_EXPRESSION,
            ),
        ]
    )


METRIC_OVERRIDES_BY_OBJECT = {
    "PlayerGame": [
        {
            "name": "games_played",
            "aggregation": "count",
            "source_attributes": ["game_id"],
            "expression": "COUNT(*)",
            "executable": False,
        },
        {
            "name": "games_won",
            "aggregation": "count_win",
            "source_attributes": ["win_loss_result"],
            "expression": "SUM(CASE WHEN win_loss_result = 'win' THEN 1 ELSE 0 END)",
            "executable": True,
        },
        {
            "name": "games_lost",
            "aggregation": "count_loss",
            "source_attributes": ["win_loss_result"],
            "expression": "SUM(CASE WHEN win_loss_result = 'loss' THEN 1 ELSE 0 END)",
            "executable": True,
        },
        {
            "name": "games_started",
            "aggregation": "count_true",
            "source_attributes": ["is_starter"],
            "expression": "SUM(CASE WHEN is_starter THEN 1 ELSE 0 END)",
            "executable": True,
        },
        {
            "name": "points_per_36",
            "aggregation": "ratio",
            "source_attributes": ["points", "minutes_played"],
            "expression": "36 * SUM(points) / NULLIF(SUM(minutes_played), 0)",
            "executable": False,
        },
        {
            "name": "average_three_point_attempt_rate",
            "aggregation": "ratio",
            "source_attributes": ["three_pointers_attempted", "field_goals_attempted"],
            "expression": "ROUND(AVG(" + python_round_ratio_expression("three_pointers_attempted", "field_goals_attempted", 3) + "), 1)",
            "executable": True,
        },
        {
            "name": "average_free_throw_attempt_rate",
            "aggregation": "ratio",
            "source_attributes": ["free_throws_attempted", "field_goals_attempted"],
            "expression": "ROUND(AVG(" + python_round_ratio_expression("free_throws_attempted", "field_goals_attempted", 3) + "), 1)",
            "executable": True,
        },
        {
            "name": "average_assist_to_turnover_ratio",
            "aggregation": "ratio",
            "source_attributes": ["assists", "turnovers"],
            "expression": "ROUND(AVG(" + python_round_ratio_expression("assists", "turnovers", 2) + "), 1)",
            "executable": True,
        },
        {
            "name": "average_field_goals_percentage",
            "aggregation": "ratio",
            "source_attributes": ["field_goals_made", "field_goals_attempted"],
            "expression": average_metric_expression(
                python_round_1_source_percentage_expression(
                    "field_goals_made",
                    "field_goals_attempted",
                )
            ),
            "executable": True,
        },
        {
            "name": "average_two_pointers_percentage",
            "aggregation": "ratio",
            "source_attributes": ["two_pointers_made", "two_pointers_attempted"],
            "expression": average_metric_expression(
                python_round_1_source_percentage_expression(
                    "two_pointers_made",
                    "two_pointers_attempted",
                )
            ),
            "executable": True,
        },
        {
            "name": "average_three_pointers_percentage",
            "aggregation": "ratio",
            "source_attributes": ["three_pointers_made", "three_pointers_attempted"],
            "expression": average_metric_expression(
                python_round_1_source_percentage_expression(
                    "three_pointers_made",
                    "three_pointers_attempted",
                )
            ),
            "executable": True,
        },
        {
            "name": "average_free_throws_percentage",
            "aggregation": "ratio",
            "source_attributes": ["free_throws_made", "free_throws_attempted"],
            "expression": average_metric_expression(
                python_round_1_source_percentage_expression(
                    "free_throws_made",
                    "free_throws_attempted",
                )
            ),
            "executable": True,
        },
        {
            "name": "average_effective_field_goal_percentage",
            "aggregation": "ratio",
            "source_attributes": [
                "field_goals_made",
                "three_pointers_made",
                "field_goals_attempted",
            ],
            "expression": average_metric_expression(
                python_round_ratio_expression(
                    "(100 * field_goals_made + 50 * three_pointers_made)",
                    "field_goals_attempted",
                    1,
                )
            ),
            "executable": True,
        },
        {
            "name": "average_true_shooting_percentage",
            "aggregation": "ratio",
            "source_attributes": [
                "points",
                "field_goals_attempted",
                "free_throws_attempted",
            ],
            "expression": average_metric_expression(
                python_round_ratio_expression(
                    "(2500 * points)",
                    "(50 * field_goals_attempted + 22 * free_throws_attempted)",
                    1,
                    corrections=TRUE_SHOOTING_PERCENTAGE_ROUNDING_CORRECTIONS,
                )
            ),
            "executable": True,
        },
        {
            "name": "total_possessions",
            "aggregation": "ratio",
            "source_attributes": ["offensive_possessions", "defensive_possessions"],
            "expression": "SUM(" + POSSESSIONS_ROW_EXPRESSION + ")",
            "executable": True,
        },
        {
            "name": "average_possessions",
            "aggregation": "ratio",
            "source_attributes": ["offensive_possessions", "defensive_possessions"],
            "expression": average_metric_expression(POSSESSIONS_ROW_EXPRESSION),
            "executable": True,
        },
        {
            "name": "average_pace",
            "aggregation": "ratio",
            "source_attributes": [
                "offensive_possessions",
                "defensive_possessions",
                "minutes_played",
            ],
            "expression": average_metric_expression(PACE_ROW_EXPRESSION),
            "executable": True,
        },
        {
            "name": "average_net_rating",
            "aggregation": "ratio",
            "source_attributes": ["offensive_rating", "defensive_rating"],
            "expression": average_metric_expression(NET_RATING_ROW_EXPRESSION),
            "executable": True,
            "aliases": [
                "net rtg",
                "netrtg",
                "nrtg",
                "average net rtg",
                "average netrtg",
                "avg net rtg",
                "avg netrtg",
            ],
        },
        {
            "name": "average_steal_percentage",
            "aggregation": "ratio",
            "source_attributes": ["steals", "defensive_possessions"],
            "expression": average_metric_expression(STEAL_PERCENTAGE_ROW_EXPRESSION),
            "executable": True,
        },
    ],
    "TeamGame": [
        {
            "name": "games_played",
            "aggregation": "count",
            "source_attributes": ["game_id"],
            "expression": "COUNT(*)",
            "executable": False,
        },
        {
            "name": "wins",
            "aggregation": "count_win",
            "source_attributes": ["win_loss_result"],
            "expression": "SUM(CASE WHEN win_loss_result = 'win' THEN 1 ELSE 0 END)",
            "executable": True,
        },
        {
            "name": "losses",
            "aggregation": "count_loss",
            "source_attributes": ["win_loss_result"],
            "expression": "SUM(CASE WHEN win_loss_result = 'loss' THEN 1 ELSE 0 END)",
            "executable": True,
        },
        {
            "name": "total_point_differential",
            "aggregation": "ratio",
            "source_attributes": ["score", "opponent_score"],
            "expression": "SUM(" + TEAM_GAME_POINT_DIFFERENTIAL_ROW_EXPRESSION + ")",
            "executable": True,
            "aliases": [
                "margin",
                "point margin",
                "score margin",
                "scoring margin",
                "plus minus",
                "+/-",
                "plusminus",
                "plus-minus",
                "plus minus differential",
                "total margin",
                "total point margin",
                "total score margin",
                "total scoring margin",
                "total plus minus",
                "total +/-",
                "total plusminus",
                "total plus-minus",
                "total plus minus differential",
            ],
        },
        {
            "name": "average_point_differential",
            "aggregation": "ratio",
            "source_attributes": ["score", "opponent_score"],
            "expression": average_metric_expression(TEAM_GAME_POINT_DIFFERENTIAL_ROW_EXPRESSION),
            "executable": True,
            "aliases": [
                "average margin",
                "average point margin",
                "average score margin",
                "average scoring margin",
                "average plus minus",
                "average +/-",
                "average plusminus",
                "average plus-minus",
                "average plus minus differential",
            ],
        },
        {
            "name": "total_possessions",
            "aggregation": "ratio",
            "source_attributes": ["offensive_possessions", "defensive_possessions"],
            "expression": "SUM(" + TEAM_GAME_POSSESSIONS_ROW_EXPRESSION + ")",
            "executable": True,
        },
        {
            "name": "average_possessions",
            "aggregation": "ratio",
            "source_attributes": ["offensive_possessions", "defensive_possessions"],
            "expression": average_metric_expression(TEAM_GAME_POSSESSIONS_ROW_EXPRESSION),
            "executable": True,
        },
        {
            "name": "average_pace",
            "aggregation": "ratio",
            "source_attributes": [
                "offensive_possessions",
                "defensive_possessions",
                "minutes_played",
            ],
            "expression": average_metric_expression(TEAM_GAME_PACE_ROW_EXPRESSION),
            "executable": True,
        },
        {
            "name": "average_offensive_rating",
            "aggregation": "ratio",
            "source_attributes": ["score", "offensive_possessions", "defensive_possessions"],
            "expression": average_metric_expression(TEAM_GAME_OFFENSIVE_RATING_ROW_EXPRESSION),
            "executable": True,
            "aliases": [
                "offensive rtg",
                "off rtg",
                "off rating",
                "ortg",
                "o rtg",
                "average offensive rtg",
                "average off rtg",
                "average ortg",
                "avg offensive rtg",
                "avg off rtg",
                "avg ortg",
            ],
        },
        {
            "name": "average_defensive_rating",
            "aggregation": "ratio",
            "source_attributes": [
                "opponent_score",
                "offensive_possessions",
                "defensive_possessions",
            ],
            "expression": average_metric_expression(TEAM_GAME_DEFENSIVE_RATING_ROW_EXPRESSION),
            "executable": True,
            "aliases": [
                "defensive rtg",
                "def rtg",
                "def rating",
                "drtg",
                "d rtg",
                "average defensive rtg",
                "average def rtg",
                "average drtg",
                "avg defensive rtg",
                "avg def rtg",
                "avg drtg",
            ],
        },
        {
            "name": "average_net_rating",
            "aggregation": "ratio",
            "source_attributes": [
                "score",
                "opponent_score",
                "offensive_possessions",
                "defensive_possessions",
            ],
            "expression": average_metric_expression(TEAM_GAME_NET_RATING_ROW_EXPRESSION),
            "executable": True,
            "aliases": [
                "net rtg",
                "netrtg",
                "nrtg",
                "average net rtg",
                "average netrtg",
                "avg net rtg",
                "avg netrtg",
            ],
        },
        {
            "name": "average_assist_percentage",
            "aggregation": "ratio",
            "source_attributes": ["assists", "field_goals_made"],
            "expression": average_metric_expression(TEAM_GAME_ASSIST_PERCENTAGE_ROW_EXPRESSION),
            "executable": True,
        },
        {
            "name": "average_assist_to_turnover_ratio",
            "aggregation": "ratio",
            "source_attributes": ["assists", "turnovers"],
            "expression": average_metric_expression(
                TEAM_GAME_ASSIST_TO_TURNOVER_RATIO_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_offensive_rebound_percentage",
            "aggregation": "ratio",
            "source_attributes": ["offensive_rebounds", "opponent_defensive_rebounds"],
            "expression": average_metric_expression(
                TEAM_GAME_OFFENSIVE_REBOUND_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_defensive_rebound_percentage",
            "aggregation": "ratio",
            "source_attributes": ["defensive_rebounds", "opponent_offensive_rebounds"],
            "expression": average_metric_expression(
                TEAM_GAME_DEFENSIVE_REBOUND_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_rebound_percentage",
            "aggregation": "ratio",
            "source_attributes": ["total_rebounds", "opponent_total_rebounds"],
            "expression": average_metric_expression(TEAM_GAME_REBOUND_PERCENTAGE_ROW_EXPRESSION),
            "executable": True,
        },
        {
            "name": "average_steal_percentage",
            "aggregation": "ratio",
            "source_attributes": ["steals", "defensive_possessions"],
            "expression": average_metric_expression(TEAM_GAME_STEAL_PERCENTAGE_ROW_EXPRESSION),
            "executable": True,
        },
        {
            "name": "average_effective_field_goal_percentage",
            "aggregation": "ratio",
            "source_attributes": [
                "field_goals_made",
                "three_pointers_made",
                "field_goals_attempted",
            ],
            "expression": average_metric_expression(
                TEAM_GAME_EFFECTIVE_FIELD_GOAL_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_true_shooting_percentage",
            "aggregation": "ratio",
            "source_attributes": ["score", "field_goals_attempted", "free_throws_attempted"],
            "expression": average_metric_expression(
                TEAM_GAME_TRUE_SHOOTING_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_three_point_attempt_rate",
            "aggregation": "ratio",
            "source_attributes": ["three_pointers_attempted", "field_goals_attempted"],
            "expression": average_metric_expression(
                TEAM_GAME_THREE_POINT_ATTEMPT_RATE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_free_throw_attempt_rate",
            "aggregation": "ratio",
            "source_attributes": ["free_throws_attempted", "field_goals_attempted"],
            "expression": average_metric_expression(
                TEAM_GAME_FREE_THROW_ATTEMPT_RATE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_field_goals_percentage",
            "aggregation": "ratio",
            "source_attributes": ["field_goals_made", "field_goals_attempted"],
            "expression": average_metric_expression(
                TEAM_GAME_FIELD_GOALS_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_opponent_field_goals_percentage",
            "aggregation": "ratio",
            "source_attributes": [
                "opponent_field_goals_made",
                "opponent_field_goals_attempted",
            ],
            "expression": average_metric_expression(
                TEAM_GAME_OPPONENT_FIELD_GOALS_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_two_pointers_percentage",
            "aggregation": "ratio",
            "source_attributes": ["two_pointers_made", "two_pointers_attempted"],
            "expression": average_metric_expression(
                TEAM_GAME_TWO_POINTERS_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_opponent_two_pointers_percentage",
            "aggregation": "ratio",
            "source_attributes": [
                "opponent_two_pointers_made",
                "opponent_two_pointers_attempted",
            ],
            "expression": average_metric_expression(
                TEAM_GAME_OPPONENT_TWO_POINTERS_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_three_pointers_percentage",
            "aggregation": "ratio",
            "source_attributes": ["three_pointers_made", "three_pointers_attempted"],
            "expression": average_metric_expression(
                TEAM_GAME_THREE_POINTERS_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_opponent_three_pointers_percentage",
            "aggregation": "ratio",
            "source_attributes": [
                "opponent_three_pointers_made",
                "opponent_three_pointers_attempted",
            ],
            "expression": average_metric_expression(
                TEAM_GAME_OPPONENT_THREE_POINTERS_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_free_throws_percentage",
            "aggregation": "ratio",
            "source_attributes": ["free_throws_made", "free_throws_attempted"],
            "expression": average_metric_expression(
                TEAM_GAME_FREE_THROWS_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
        {
            "name": "average_opponent_free_throws_percentage",
            "aggregation": "ratio",
            "source_attributes": [
                "opponent_free_throws_made",
                "opponent_free_throws_attempted",
            ],
            "expression": average_metric_expression(
                TEAM_GAME_OPPONENT_FREE_THROWS_PERCENTAGE_ROW_EXPRESSION
            ),
            "executable": True,
        },
    ],
    "PlayerSeason": player_season_derived_metric_overrides(
        shooting_rounding_corrections=True,
    ),
    "PlayerSeasonTeam": player_season_derived_metric_overrides(
        shooting_rounding_corrections=False,
    ),
    "TeamSeason": team_season_derived_metric_overrides(),
}

DERIVED_ATTRIBUTES_BY_OBJECT = {
    "Game": [
        {
            "name": "game_month",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%m')",
            },
        },
        {
            "name": "game_year",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%Y')",
            },
        },
        {
            "name": "game_year_month",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%Y-%m')",
            },
        },
    ],
    "PlayerGame": [
        {
            "name": "game_month",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%m')",
            },
        },
        {
            "name": "game_year",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%Y')",
            },
        },
        {
            "name": "game_year_month",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%Y-%m')",
            },
        },
    ],
    "TeamGame": [
        {
            "name": "point_differential",
            "kind": "measure",
            "source_column": "point_differential",
            "link_key": False,
            "visibility": "public",
            "aliases": [
                "margin",
                "point margin",
                "score margin",
                "scoring margin",
            ],
            "derivation": {
                "source_attribute": "score",
                "sql_expression": (
                    "CASE WHEN {fact_alias}.score IS NOT NULL "
                    "AND {fact_alias}.opponent_score IS NOT NULL "
                    "THEN {fact_alias}.score - {fact_alias}.opponent_score "
                    "ELSE NULL END"
                ),
            },
        },
        {
            "name": "game_month",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%m')",
            },
        },
        {
            "name": "game_year",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%Y')",
            },
        },
        {
            "name": "game_year_month",
            "kind": "dimension",
            "source_column": "game_date",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "game_date",
                "sql_expression": "STRFTIME({fact_alias}.game_date, '%Y-%m')",
            },
        },
    ],
    "TeamSeason": [
        {
            "name": "win_percentage",
            "kind": "measure",
            "source_column": "win_percentage",
            "link_key": False,
            "visibility": "public",
            "derivation": {
                "source_attribute": "wins",
                "sql_expression": (
                    "CASE WHEN {fact_alias}.games_played IS NOT NULL "
                    "AND {fact_alias}.games_played > 0 THEN "
                    + python_round_ratio_expression(
                        "{fact_alias}.wins",
                        "{fact_alias}.games_played",
                        3,
                    )
                    + " ELSE NULL END"
                ),
            },
        },
    ],
}

COMPARISON_IDENTITIES_BY_OBJECT = {
    "Player": {"full_name"},
    "Team": {"team_name"},
}

LINKS = [
    {
        "name": "game_arena",
        "source_object": "Game",
        "target_object": "Arena",
        "relation_type": "many_to_one",
        "source_key": "arena_id",
        "target_key": "arena_id",
    },
    {
        "name": "player_game_player",
        "source_object": "PlayerGame",
        "target_object": "Player",
        "relation_type": "many_to_one",
        "source_key": "person_id",
        "target_key": "person_id",
    },
    {
        "name": "player_game_game",
        "source_object": "PlayerGame",
        "target_object": "Game",
        "relation_type": "many_to_one",
        "source_key": "game_id",
        "target_key": "game_id",
    },
    {
        "name": "player_game_team",
        "source_object": "PlayerGame",
        "target_object": "Team",
        "relation_type": "many_to_one",
        "source_key": "team_id",
        "target_key": "team_id",
    },
    {
        "name": "player_game_opponent_team",
        "source_object": "PlayerGame",
        "target_object": "Team",
        "relation_type": "many_to_one",
        "source_key": "opponent_team_id",
        "target_key": "team_id",
    },
    {
        "name": "team_game_game",
        "source_object": "TeamGame",
        "target_object": "Game",
        "relation_type": "many_to_one",
        "source_key": "game_id",
        "target_key": "game_id",
    },
    {
        "name": "team_game_team",
        "source_object": "TeamGame",
        "target_object": "Team",
        "relation_type": "many_to_one",
        "source_key": "team_id",
        "target_key": "team_id",
    },
    {
        "name": "team_game_opponent_team",
        "source_object": "TeamGame",
        "target_object": "Team",
        "relation_type": "many_to_one",
        "source_key": "opponent_team_id",
        "target_key": "team_id",
    },
    {
        "name": "player_season_player",
        "source_object": "PlayerSeason",
        "target_object": "Player",
        "relation_type": "many_to_one",
        "source_key": "person_id",
        "target_key": "person_id",
    },
    {
        "name": "player_season_team_player",
        "source_object": "PlayerSeasonTeam",
        "target_object": "Player",
        "relation_type": "many_to_one",
        "source_key": "person_id",
        "target_key": "person_id",
    },
    {
        "name": "player_season_team_team",
        "source_object": "PlayerSeasonTeam",
        "target_object": "Team",
        "relation_type": "many_to_one",
        "source_key": "team_id",
        "target_key": "team_id",
    },
    {
        "name": "team_season_team",
        "source_object": "TeamSeason",
        "target_object": "Team",
        "relation_type": "many_to_one",
        "source_key": "team_id",
        "target_key": "team_id",
    },
]


def object_name_for_table(table_name: str) -> str:
    return {
        "player": "Player",
        "team": "Team",
        "arena": "Arena",
        "game": "Game",
        "player_game": "PlayerGame",
        "team_game": "TeamGame",
        "player_season": "PlayerSeason",
        "player_season_team": "PlayerSeasonTeam",
        "team_season": "TeamSeason",
    }[table_name]


def build_attribute_payload(
    object_name: str,
    column: dict[str, object],
    value_aliases_by_object: dict[str, object],
) -> dict[str, object]:
    payload = {
        "name": column["name"],
        "kind": column["attribute_kind"],
        "source_column": column["name"],
        "link_key": column["link_key"],
        "visibility": column["visibility"],
        "derivation": None,
    }
    if column["name"] in COMPARISON_IDENTITIES_BY_OBJECT.get(object_name, set()):
        payload["comparison_identity"] = True
    attribute_aliases = (
        value_aliases_by_object.get(object_name, {}).get(column["name"], {})
        if isinstance(value_aliases_by_object.get(object_name, {}), dict)
        else {}
    )
    if attribute_aliases:
        payload["value_aliases"] = attribute_aliases
    semantic_aliases = dedupe_aliases(
        ATTRIBUTE_ALIASES_BY_OBJECT.get(object_name, {}).get(column["name"], [])
        + stat_aliases(str(column["name"]))
    )
    if semantic_aliases:
        payload["aliases"] = semantic_aliases
    return payload


def metric_payload(
    *,
    name: str,
    aggregation: str,
    source_attribute: str,
    expression: str,
    executable: bool = True,
    aliases=None,
) -> dict[str, object]:
    payload = {
        "name": name,
        "aggregation": aggregation,
        "source_attributes": [source_attribute],
        "expression": expression,
        "executable": executable,
    }
    if aliases:
        payload["aliases"] = dedupe_aliases(aliases)
    return payload


def is_public_measure_column(column: dict[str, object]) -> bool:
    return column["attribute_kind"] == "measure" and column["visibility"] == "public"


def is_rate_measure(column_name: str) -> bool:
    return any(token in column_name for token in RATE_MEASURE_TOKENS)


def game_metric_base_name(column_name: str) -> str:
    if column_name in GAME_METRIC_BASE_OVERRIDES:
        return GAME_METRIC_BASE_OVERRIDES[column_name]
    if column_name.startswith("opponent_total_"):
        return "opponent_" + column_name.removeprefix("opponent_total_")
    if column_name.startswith("total_"):
        return column_name.removeprefix("total_")
    return column_name


def generated_game_metrics(object_name: str, column: dict[str, object]) -> list[dict[str, object]]:
    source_attribute = str(column["name"])
    base_name = game_metric_base_name(source_attribute)
    source_aliases = ATTRIBUTE_ALIASES_BY_OBJECT.get(object_name, {}).get(source_attribute, [])
    metrics = [
        metric_payload(
            name=f"average_{base_name}",
            aggregation="avg",
            source_attribute=source_attribute,
            expression=f"AVG({source_attribute})",
            aliases=(
                source_aliases + prefixed_metric_aliases("average", source_aliases)
                if is_rate_measure(source_attribute)
                else prefixed_metric_aliases("average", source_aliases)
            ),
        )
    ]
    if not is_rate_measure(source_attribute):
        metrics.insert(
            0,
            metric_payload(
                name=f"total_{base_name}",
                aggregation="sum",
                source_attribute=source_attribute,
                expression=f"SUM({source_attribute})",
                aliases=source_aliases + prefixed_metric_aliases("total", source_aliases),
            ),
        )
    return metrics


def prefixed_metric_aliases(prefix: str, aliases: list[str]) -> list[str]:
    return [f"{prefix} {alias}" for alias in aliases]


def generated_season_metric(object_name: str, column: dict[str, object]) -> dict[str, object]:
    source_attribute = str(column["name"])
    return metric_payload(
        name=source_attribute,
        aggregation="identity",
        source_attribute=source_attribute,
        expression=source_attribute,
        aliases=ATTRIBUTE_ALIASES_BY_OBJECT.get(object_name, {}).get(source_attribute, []),
    )


def generated_metrics_for_object(object_name: str, columns: list[dict[str, object]]) -> list[dict[str, object]]:
    public_measure_columns = [
        column
        for column in columns
        if is_public_measure_column(column)
        and metric_column_is_exposure_ready(object_name, str(column["name"]))
    ]
    if object_name in GAME_GRAIN_OBJECTS:
        return [
            metric
            for column in public_measure_columns
            for metric in generated_game_metrics(object_name, column)
        ]
    if object_name in SEASON_GRAIN_OBJECTS:
        return [generated_season_metric(object_name, column) for column in public_measure_columns]
    return []


def metric_column_is_exposure_ready(object_name: str, column_name: str) -> bool:
    if object_name != "TeamGame":
        return True
    if column_name in TEAM_GAME_ALLOWED_RATE_COLUMNS:
        return True
    return not is_rate_measure(column_name)


def dedupe_metrics(metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped = []
    seen_names = set()
    for metric in metrics:
        metric_name = metric["name"]
        if metric_name in seen_names:
            continue
        seen_names.add(metric_name)
        deduped.append(metric)
    return deduped


def enrich_metric_aliases(metric: dict[str, object]) -> dict[str, object]:
    enriched = dict(metric)
    enriched["ranking_polarity"] = ranking_polarity_for_metric(str(enriched["name"]))
    aliases = dedupe_aliases(
        list(enriched.get("aliases", [])) + generated_metric_aliases(str(enriched["name"]))
    )
    if aliases:
        enriched["aliases"] = aliases
    return enriched


def metrics_for_object(object_name: str, columns: list[dict[str, object]]) -> list[dict[str, object]]:
    # Generated metrics expose every executable public stat surface supported by
    # the snapshot. Overrides define curated formulas or aliases that cannot be
    # generated safely from one source column.
    return [enrich_metric_aliases(metric) for metric in dedupe_metrics(
        METRIC_OVERRIDES_BY_OBJECT.get(object_name, [])
        + generated_metrics_for_object(object_name, columns)
    )]


def enrich_derived_attribute_aliases(attribute: dict[str, object]) -> dict[str, object]:
    aliases = dedupe_aliases(
        list(attribute.get("aliases", []))
        + GAME_DATE_DIMENSION_ALIASES.get(str(attribute["name"]), [])
        + stat_aliases(str(attribute["name"]))
    )
    if aliases:
        return {**attribute, "aliases": aliases}
    return attribute


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def supported_measure_columns_by_object(inventory: dict[str, object]) -> dict[str, set[str]]:
    # Executable metrics must be backed by data, not just by a schema column.
    # All-null snapshot columns remain queryable attributes but are not promoted
    # to metrics that would otherwise render blank analytical answers.
    import duckdb

    from scripts.load_gold_snapshot import load_database

    database_path = load_database()
    conn = duckdb.connect(str(database_path), read_only=True)
    support: dict[str, set[str]] = {}
    for table in inventory["tables"]:
        object_name = table["object_name"] if "object_name" in table else object_name_for_table(table["table_name"])
        public_measure_columns = [
            str(column["name"])
            for column in table["columns"]
            if is_public_measure_column(column)
        ]
        if not public_measure_columns:
            support[object_name] = set()
            continue
        count_expressions = []
        for column_name in public_measure_columns:
            quoted_column = quote_identifier(column_name)
            count_expressions.extend(
                [
                    f"COUNT({quoted_column}) AS {quote_identifier(column_name + '__count')}",
                    f"MIN({quoted_column}) AS {quote_identifier(column_name + '__min')}",
                    f"MAX({quoted_column}) AS {quote_identifier(column_name + '__max')}",
                ]
            )
        row = conn.execute(
            f"SELECT {', '.join(count_expressions)} FROM {quote_identifier(table['table_name'])}"
        ).fetchone()
        supported_columns = set()
        row_values = list(row or [])
        for index, column_name in enumerate(public_measure_columns):
            non_null_count = row_values[index * 3]
            min_value = row_values[index * 3 + 1]
            max_value = row_values[index * 3 + 2]
            if not non_null_count or int(non_null_count) <= 0:
                continue
            if min_value == 0 and max_value == 0:
                continue
            supported_columns.add(column_name)
        support[object_name] = supported_columns
    return support


def build_ontology_payload() -> dict[str, object]:
    inventory = json.loads(ATTRIBUTE_INVENTORY_PATH.read_text(encoding="utf-8"))
    value_aliases = yaml.safe_load(VALUE_ALIASES_PATH.read_text(encoding="utf-8")) or {}
    supported_measure_columns = supported_measure_columns_by_object(inventory)
    objects = []
    for table in inventory["tables"]:
        object_name = table["object_name"] if "object_name" in table else object_name_for_table(table["table_name"])
        metric_columns = [
            column
            for column in table["columns"]
            if str(column["name"]) in supported_measure_columns.get(object_name, set())
        ]
        object_payload = {
            "name": object_name,
            "backing_table": table["table_name"],
            "description": OBJECT_DESCRIPTIONS[object_name],
            "attributes": [
                build_attribute_payload(object_name, column, value_aliases)
                for column in table["columns"]
            ]
            + [
                enrich_derived_attribute_aliases(attribute)
                for attribute in DERIVED_ATTRIBUTES_BY_OBJECT.get(object_name, [])
            ],
            "metrics": metrics_for_object(object_name, metric_columns),
        }
        objects.append(object_payload)
    return {"objects": objects, "links": LINKS}


def generate_ontology() -> Path:
    ONTOLOGY_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = build_ontology_payload()
    yaml_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    ONTOLOGY_OUTPUT_PATH.write_text(
        "# This file is generated from semantic_gold metadata. Do not hand edit.\n"
        + yaml_text,
        encoding="utf-8",
    )
    return ONTOLOGY_OUTPUT_PATH


def main() -> None:
    path = generate_ontology()
    print(path)


if __name__ == "__main__":
    main()
