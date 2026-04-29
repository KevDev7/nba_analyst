#!/usr/bin/env python3
# Purpose:
# Generate ontology value aliases from the local semantic_gold DuckDB snapshot.
#
# Uses:
# - fixtures/duckdb/gold_slice.duckdb
# - pipelines/athena/metadata/semantic_gold_curated_value_aliases.yaml
#
# Produces:
# - pipelines/athena/metadata/semantic_gold_value_aliases.yaml
#
# Next:
# - scripts/generate_semantic_ontology.py merges this artifact into semantic-gold.yaml

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys
from typing import Iterable, Optional

import duckdb
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.load_gold_snapshot import load_database


CURATED_ALIASES_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_curated_value_aliases.yaml"
)
OUTPUT_PATH = ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_value_aliases.yaml"


ValueAliases = dict[str, dict[str, dict[str, list[str]]]]
AliasRows = Iterable[tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]]


def normalized_alias(value: object) -> str:
    return "".join(character.lower() for character in str(value).strip() if character.isalnum())


def add_alias(
    aliases: ValueAliases,
    object_name: str,
    attribute_name: str,
    canonical_value: object,
    alias_value: object,
) -> None:
    canonical_text = str(canonical_value).strip()
    alias_text = str(alias_value).strip()
    if not canonical_text or not alias_text:
        return
    values = aliases.setdefault(object_name, {}).setdefault(attribute_name, {}).setdefault(canonical_text, [])
    if alias_text not in values:
        values.append(alias_text)


def add_team_identity_aliases(
    aliases: ValueAliases,
    *,
    team_name: str,
    team_city: str,
    team_abbreviation: str,
) -> None:
    # These aliases come directly from one semantic_gold.team row. City-only
    # aliases are intentionally omitted because values like "Los Angeles" can
    # refer to more than one NBA team.
    city_team_name = f"{team_city} {team_name}".strip()

    for alias_value in [team_name, team_abbreviation, city_team_name]:
        add_alias(aliases, "Team", "team_name", team_name, alias_value)

    for alias_value in [team_abbreviation, team_name, city_team_name]:
        add_alias(aliases, "Team", "team_abbreviation", team_abbreviation, alias_value)


def add_conference_aliases(aliases: ValueAliases, conference: str) -> None:
    alias_values = [conference, f"{conference} conference"]
    if conference == "east":
        alias_values.extend(["eastern", "eastern conference"])
    elif conference == "west":
        alias_values.extend(["western", "western conference"])
    for alias_value in alias_values:
        add_alias(aliases, "Team", "conference", conference, alias_value)


def add_division_aliases(aliases: ValueAliases, division: str) -> None:
    for alias_value in [division, f"{division} division"]:
        add_alias(aliases, "Team", "division", division, alias_value)


def build_team_value_aliases(team_rows: AliasRows) -> ValueAliases:
    aliases: ValueAliases = {}
    for team_name, team_city, team_abbreviation, conference, division in team_rows:
        if team_name and team_city and team_abbreviation:
            add_team_identity_aliases(
                aliases,
                team_name=str(team_name),
                team_city=str(team_city),
                team_abbreviation=str(team_abbreviation),
            )
        if conference:
            add_conference_aliases(aliases, str(conference))
        if division:
            add_division_aliases(aliases, str(division))
    return aliases


def load_team_rows(database_path: Path) -> list[tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]]:
    conn = duckdb.connect(str(database_path), read_only=True)
    try:
        return conn.execute(
            """
            SELECT DISTINCT
              team_name,
              team_city,
              team_abbreviation,
              conference,
              division
            FROM team
            ORDER BY team_name
            """
        ).fetchall()
    finally:
        conn.close()


def load_curated_aliases(path: Path = CURATED_ALIASES_PATH) -> ValueAliases:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def merge_aliases(base: ValueAliases, curated_aliases: ValueAliases) -> ValueAliases:
    merged: ValueAliases = {}
    for source in [base, curated_aliases]:
        for object_name, attributes in source.items():
            for attribute_name, canonical_values in attributes.items():
                for canonical_value, alias_values in canonical_values.items():
                    for alias_value in alias_values:
                        add_alias(merged, object_name, attribute_name, canonical_value, alias_value)
    return merged


def ambiguous_aliases(aliases: ValueAliases) -> dict[tuple[str, str, str], list[str]]:
    ambiguity: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for object_name, attributes in aliases.items():
        for attribute_name, canonical_values in attributes.items():
            for canonical_value, alias_values in canonical_values.items():
                for alias_value in [canonical_value, *alias_values]:
                    normalized_value = normalized_alias(alias_value)
                    if normalized_value:
                        ambiguity[(object_name, attribute_name, normalized_value)].add(canonical_value)
    return {
        key: sorted(canonical_values)
        for key, canonical_values in ambiguity.items()
        if len(canonical_values) > 1
    }


def validate_unambiguous_aliases(aliases: ValueAliases) -> None:
    ambiguous = ambiguous_aliases(aliases)
    if not ambiguous:
        return
    first_key = next(iter(ambiguous))
    object_name, attribute_name, alias_value = first_key
    canonical_values = ", ".join(ambiguous[first_key])
    raise ValueError(
        f"Ambiguous value alias '{alias_value}' for {object_name}.{attribute_name}: {canonical_values}."
    )


def build_value_aliases(database_path: Path) -> ValueAliases:
    data_backed_aliases = build_team_value_aliases(load_team_rows(database_path))
    aliases = merge_aliases(data_backed_aliases, load_curated_aliases())
    validate_unambiguous_aliases(aliases)
    return aliases


def write_value_aliases(aliases: ValueAliases, output_path: Path = OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = yaml.safe_dump(aliases, sort_keys=False, allow_unicode=True)
    output_path.write_text(
        "# This file is generated from semantic_gold DuckDB values and curated aliases. Do not hand edit.\n"
        + yaml_text,
        encoding="utf-8",
    )
    return output_path


def generate_value_aliases() -> Path:
    database_path = load_database()
    aliases = build_value_aliases(database_path)
    return write_value_aliases(aliases)


def main() -> None:
    print(generate_value_aliases())


if __name__ == "__main__":
    main()
