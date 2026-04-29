from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import yaml

from scripts.load_gold_snapshot import load_database


ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
SINGLE_TOKEN_NAME_PARTS = {
    "firstname",
    "lastname",
    "teamabbreviation",
    "abbreviation",
}


class EntityResolutionError(RuntimeError):
    """Raised when raw entity phrases cannot be safely resolved from the snapshot."""


@dataclass(frozen=True)
class EntityResolverSpec:
    object_name: str
    table_name: str
    id_column: str
    identity_column: str
    subject_key: str
    single_token_columns: tuple[str, ...]


def _normalized(value: object) -> str:
    return "".join(character.lower() for character in str(value).strip() if character.isalnum())


def _singular_key(value: object) -> str:
    key = _normalized(value)
    return key[:-1] if key.endswith("s") else key


def _subject_key(value: object) -> str:
    key = _singular_key(value)
    for noise_word in ["nba", "basketball", "league"]:
        key = key.replace(noise_word, "")
    return key


@lru_cache(maxsize=1)
def _resolver_specs_by_subject() -> dict[str, EntityResolverSpec]:
    ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    specs: dict[str, EntityResolverSpec] = {}
    for object_payload in ontology["objects"]:
        comparison_identity = next(
            (
                attribute
                for attribute in object_payload["attributes"]
                if attribute.get("comparison_identity") is True
            ),
            None,
        )
        if comparison_identity is None:
            continue
        primary_key = next(
            (
                attribute
                for attribute in object_payload["attributes"]
                if attribute.get("kind") == "primary_key"
            ),
            None,
        )
        if primary_key is None:
            continue

        identity_column = str(comparison_identity["source_column"])
        token_columns = [
            str(attribute["source_column"])
            for attribute in object_payload["attributes"]
            if attribute.get("kind") == "dimension"
            and attribute.get("source_column")
            and _normalized(attribute["name"]) in SINGLE_TOKEN_NAME_PARTS
        ]
        if _normalized(comparison_identity["name"]) != "fullname":
            token_columns.insert(0, identity_column)

        object_name = str(object_payload["name"])
        subject_key = _subject_key(object_name)
        specs[subject_key] = EntityResolverSpec(
            object_name=object_name,
            table_name=str(object_payload["backing_table"]),
            id_column=str(primary_key["source_column"]),
            identity_column=identity_column,
            subject_key=subject_key,
            single_token_columns=tuple(dict.fromkeys(token_columns)),
        )
    return specs


def _resolver_spec_for_subject(subject: str) -> EntityResolverSpec:
    subject_key = _subject_key(subject)
    matches = [
        spec
        for spec in _resolver_specs_by_subject().values()
        if subject_key == spec.subject_key or spec.subject_key in subject_key
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(spec.object_name for spec in matches)
        raise EntityResolutionError(
            f"Comparison subject '{subject}' is ambiguous across ontology objects: {names}."
        )
    raise EntityResolutionError(
        f"Could not infer a supported comparison entity family from subject '{subject}'."
    )


def _exact_identity_matches(conn: duckdb.DuckDBPyConnection, spec: EntityResolverSpec, phrase: str) -> list[dict[str, object]]:
    return conn.execute(
        f"""
        SELECT {spec.id_column} AS entity_id, {spec.identity_column} AS entity_name
        FROM {spec.table_name}
        WHERE lower({spec.identity_column}) = lower(?)
        """,
        [phrase],
    ).fetchall()


def _single_token_matches(conn: duckdb.DuckDBPyConnection, spec: EntityResolverSpec, phrase: str) -> list[dict[str, object]]:
    conditions = " OR ".join(f"lower({column_name}) = lower(?)" for column_name in spec.single_token_columns)
    parameters = [phrase for _ in spec.single_token_columns]
    return conn.execute(
        f"""
        SELECT DISTINCT {spec.id_column} AS entity_id, {spec.identity_column} AS entity_name
        FROM {spec.table_name}
        WHERE {conditions}
        ORDER BY {spec.identity_column}
        """,
        parameters,
    ).fetchall()


def _resolve_entity_phrase(conn: duckdb.DuckDBPyConnection, spec: EntityResolverSpec, phrase: str) -> dict[str, object]:
    cleaned_phrase = phrase.strip()
    if not cleaned_phrase:
        raise EntityResolutionError("Comparison entity phrases must be non-empty.")

    # Multi-word names must match the identity exactly. Single-token names may
    # resolve by first/last name only when the combined candidate set is unique.
    rows = _exact_identity_matches(conn, spec, cleaned_phrase)
    if not rows and len(cleaned_phrase.split()) == 1:
        rows = _single_token_matches(conn, spec, cleaned_phrase)

    if not rows:
        raise EntityResolutionError(
            f"No {spec.object_name.lower()} matched comparison entity phrase '{phrase}'."
        )

    unique_rows = {
        (int(row[0]), str(row[1]))
        for row in rows
        if row[0] is not None and row[1] is not None
    }
    if len(unique_rows) == 1:
        entity_id, entity_name = next(iter(unique_rows))
        return {"entityId": entity_id, "entityName": entity_name}

    sample_names = ", ".join(name for _entity_id, name in sorted(unique_rows)[:8])
    more_suffix = "..." if len(unique_rows) > 8 else ""
    raise EntityResolutionError(
        f"Comparison entity phrase '{phrase}' is ambiguous across {spec.object_name.lower()}s: "
        f"{sample_names}{more_suffix}."
    )


def enrich_semantic_draft_with_resolved_entities(draft: dict[str, Any]) -> dict[str, Any]:
    # Only comparison drafts need data-backed entity IDs before Haskell planning.
    if _normalized(draft.get("task", "")) != "compare":
        return draft

    raw_entities = [str(entity).strip() for entity in draft.get("entities", []) if str(entity).strip()]
    if len(raw_entities) < 2:
        raise EntityResolutionError("Comparison requires at least two raw entity names in the semantic draft.")

    spec = _resolver_spec_for_subject(str(draft.get("subject", "")))
    database_path = load_database()
    conn = duckdb.connect(str(database_path), read_only=True)
    try:
        resolved_entities = [
            _resolve_entity_phrase(conn, spec, raw_entity)
            for raw_entity in raw_entities
        ]
    finally:
        conn.close()

    if len({entity["entityId"] for entity in resolved_entities}) != len(resolved_entities):
        raise EntityResolutionError("Comparison requires distinct resolved entities.")

    enriched = dict(draft)
    enriched["resolved_entities"] = resolved_entities
    enriched["value_resolution_trace"] = {
        "entity_resolutions": [
            {
                "raw_value": raw_entity,
                "canonical_value": resolved_entity["entityName"],
                "target_object": spec.object_name,
                "attribute": spec.identity_column,
                "entity_id": resolved_entity["entityId"],
                "source": "duckdb_entity_resolver",
            }
            for raw_entity, resolved_entity in zip(raw_entities, resolved_entities)
            if raw_entity != resolved_entity["entityName"]
        ]
    }
    return enriched
