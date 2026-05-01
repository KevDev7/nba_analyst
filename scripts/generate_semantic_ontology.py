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

GAME_METRIC_BASE_OVERRIDES = {
    "score": "points",
    "opponent_score": "opponent_points",
    "minutes_played": "minutes",
}

ATTRIBUTE_ALIASES_BY_OBJECT = {
    "TeamGame": {
        "point_differential": [
            "margin",
            "point margin",
            "score margin",
            "scoring margin",
        ],
    },
}

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
    ],
    "TeamSeason": [
        {
            "name": "average_points",
            "aggregation": "identity",
            "source_attributes": ["points_per_game"],
            "expression": "points_per_game",
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
    semantic_aliases = ATTRIBUTE_ALIASES_BY_OBJECT.get(object_name, {}).get(column["name"], [])
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
        payload["aliases"] = aliases
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
            aliases=prefixed_metric_aliases("average", source_aliases),
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


def generated_season_metric(column: dict[str, object]) -> dict[str, object]:
    source_attribute = str(column["name"])
    return metric_payload(
        name=source_attribute,
        aggregation="identity",
        source_attribute=source_attribute,
        expression=source_attribute,
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
        return [generated_season_metric(column) for column in public_measure_columns]
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


def metrics_for_object(object_name: str, columns: list[dict[str, object]]) -> list[dict[str, object]]:
    # Generated metrics expose every executable public stat surface supported by
    # the snapshot. Overrides are only for semantic aliases and non-executable
    # formulas that cannot be generated safely from one source column.
    return dedupe_metrics(
        generated_metrics_for_object(object_name, columns)
        + METRIC_OVERRIDES_BY_OBJECT.get(object_name, [])
    )


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
            + DERIVED_ATTRIBUTES_BY_OBJECT.get(object_name, []),
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
