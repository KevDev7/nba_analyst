#!/usr/bin/env python3
# Purpose:
# Generate the canonical ontology artifact from semantic_gold metadata.
#
# Uses:
# - pipelines/athena/metadata/semantic_gold_attribute_inventory.json
#
# Produces:
# - fixtures/ontology/semantic-gold.yaml
#
# Next:
# - apps/cli/main.py and the Haskell ontology loader

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTE_INVENTORY_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_attribute_inventory.json"
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

METRICS_BY_OBJECT = {
    "PlayerGame": [
        {
            "name": "total_points",
            "aggregation": "sum",
            "source_attributes": ["points"],
            "expression": "SUM(points)",
            "executable": True,
        },
        {
            "name": "average_points",
            "aggregation": "avg",
            "source_attributes": ["points"],
            "expression": "AVG(points)",
            "executable": True,
        },
        {
            "name": "games_played",
            "aggregation": "count",
            "source_attributes": ["game_id"],
            "expression": "COUNT(*)",
            "executable": False,
        },
        {
            "name": "points_per_36",
            "aggregation": "ratio",
            "source_attributes": ["points", "minutes_played_decimal"],
            "expression": "36 * SUM(points) / NULLIF(SUM(minutes_played_decimal), 0)",
            "executable": False,
        },
    ],
    "TeamGame": [
        {
            "name": "total_points",
            "aggregation": "sum",
            "source_attributes": ["score"],
            "expression": "SUM(score)",
            "executable": True,
        },
        {
            "name": "average_points",
            "aggregation": "avg",
            "source_attributes": ["score"],
            "expression": "AVG(score)",
            "executable": True,
        },
        {
            "name": "games_played",
            "aggregation": "count",
            "source_attributes": ["game_id"],
            "expression": "COUNT(*)",
            "executable": False,
        },
    ],
    "PlayerSeason": [
        {
            "name": "games_played",
            "aggregation": "identity",
            "source_attributes": ["games_played"],
            "expression": "games_played",
            "executable": True,
        },
        {
            "name": "points_total",
            "aggregation": "identity",
            "source_attributes": ["points_total"],
            "expression": "points_total",
            "executable": True,
        },
        {
            "name": "points_per_game",
            "aggregation": "identity",
            "source_attributes": ["points_per_game"],
            "expression": "points_per_game",
            "executable": True,
        },
    ],
    "PlayerSeasonTeam": [
        {
            "name": "games_played",
            "aggregation": "identity",
            "source_attributes": ["games_played"],
            "expression": "games_played",
            "executable": True,
        },
        {
            "name": "points_total",
            "aggregation": "identity",
            "source_attributes": ["points_total"],
            "expression": "points_total",
            "executable": True,
        },
        {
            "name": "points_per_game",
            "aggregation": "identity",
            "source_attributes": ["points_per_game"],
            "expression": "points_per_game",
            "executable": True,
        },
    ],
    "TeamSeason": [
        {
            "name": "games_played",
            "aggregation": "identity",
            "source_attributes": ["games_played"],
            "expression": "games_played",
            "executable": True,
        },
        {
            "name": "wins",
            "aggregation": "identity",
            "source_attributes": ["wins"],
            "expression": "wins",
            "executable": True,
        },
        {
            "name": "losses",
            "aggregation": "identity",
            "source_attributes": ["losses"],
            "expression": "losses",
            "executable": True,
        },
        {
            "name": "win_percentage",
            "aggregation": "identity",
            "source_attributes": ["win_percentage"],
            "expression": "win_percentage",
            "executable": True,
        },
        {
            "name": "average_points",
            "aggregation": "identity",
            "source_attributes": ["average_points"],
            "expression": "average_points",
            "executable": True,
        },
    ],
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


def build_ontology_payload() -> dict[str, object]:
    inventory = json.loads(ATTRIBUTE_INVENTORY_PATH.read_text(encoding="utf-8"))
    objects = []
    for table in inventory["tables"]:
        object_name = table["object_name"] if "object_name" in table else object_name_for_table(table["table_name"])
        object_payload = {
            "name": object_name,
            "backing_table": table["table_name"],
            "description": OBJECT_DESCRIPTIONS[object_name],
            "attributes": [
                {
                    "name": column["name"],
                    "kind": column["attribute_kind"],
                    "source_column": column["name"],
                    "link_key": column["link_key"],
                    "visibility": column["visibility"],
                    "derivation": None,
                }
                for column in table["columns"]
            ]
            + DERIVED_ATTRIBUTES_BY_OBJECT.get(object_name, []),
            "metrics": METRICS_BY_OBJECT.get(object_name, []),
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
