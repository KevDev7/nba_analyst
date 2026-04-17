#!/usr/bin/env python3
# Purpose:
# Generate the canonical interpreter capability artifact from ontology metadata,
# planner-derived supported families, and the temporary execution exception list.
#
# Uses:
# - fixtures/ontology/semantic-gold.yaml
# - pipelines/athena/metadata/semantic_gold_attribute_inventory.json
# - pipelines/athena/metadata/semantic_interpreter_execution_contract.yaml
# - the Haskell derive-capabilities-json entrypoint
#
# Produces:
# - fixtures/interpreter/semantic-capabilities.json
#
# Next:
# - apps/cli/semantic_interpreter.py

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import duckdb
import yaml

try:
    from .load_gold_snapshot import load_database
except ImportError:  # pragma: no cover - direct script execution
    from load_gold_snapshot import load_database


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
ATTRIBUTE_INVENTORY_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_attribute_inventory.json"
)
EXECUTION_CONTRACT_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_interpreter_execution_contract.yaml"
)
HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
OUTPUT_PATH = ROOT / "fixtures" / "interpreter" / "semantic-capabilities.json"


def _normalize_player_alias(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def _public_dimension_names(object_entry: dict) -> list[str]:
    return sorted(
        attribute["name"]
        for attribute in object_entry.get("attributes", [])
        if attribute.get("visibility") == "public" and attribute.get("kind") == "dimension"
    )


def _public_attribute_names(object_entry: dict) -> list[str]:
    return sorted(
        attribute["name"]
        for attribute in object_entry.get("attributes", [])
        if attribute.get("visibility") == "public"
    )


def _executable_metric_names(object_entry: dict) -> list[str]:
    return sorted(
        metric["name"]
        for metric in object_entry.get("metrics", [])
        if metric.get("executable")
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_planner_derived_capabilities() -> dict:
    command = [
        "cabal",
        "run",
        "-v0",
        "ontology-hs",
        "--",
        "derive-capabilities-json",
        "--ontology",
        str(ONTOLOGY_PATH),
    ]
    result = subprocess.run(
        command,
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    payload_text = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(
            "derive-capabilities-json failed: "
            + (payload_text[:1000] if payload_text else "no output")
        )
    return json.loads(payload_text)


def _build_prompt_summary(families: list[dict]) -> str:
    lines = [
        "Supported semantic families (generated from ontology + planner-derived capabilities):"
    ]
    for family in families:
        dimension_text = (
            ", ".join(family["dimensions"])
            if family["dimensions"]
            else "no business grouping dimension"
        )
        filter_text = ", ".join(family["required_filter_kinds"])
        metric_text = ", ".join(family["metrics"])
        linked_text = (
            "; linked filters: "
            + ", ".join(
                f"{linked_filter['target_object']}.{linked_filter['attribute']}"
                for linked_filter in family["linked_filters"]
            )
            if family["linked_filters"]
            else ""
        )
        time_text = (
            f"; time_grain: {family['time_grain']}"
            if family["time_grain"] is not None
            else ""
        )
        row_text = (
            f"; row_object: {family['row_object']}"
            if family.get("row_object") is not None
            else ""
        )
        comparison_text = (
            "; comparison enabled"
            if family["comparison"]["enabled"]
            else ""
        )
        lines.append(
            f"- {family['family_key']}: {family['query_kind']} on {family['core_fact_object']} "
            f"with metrics [{metric_text}], dimensions [{dimension_text}], required filters "
            f"[{filter_text}]{row_text}{time_text}{linked_text}{comparison_text}"
        )
    return "\n".join(lines)


def _build_player_entity_index() -> dict:
    database_path = load_database()
    with duckdb.connect(str(database_path), read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT
              person_id,
              player_name,
              first_name,
              family_name,
              display_name
            FROM player
            """
        ).fetchall()

    players: list[dict] = []
    alias_candidates: dict[str, dict[int, dict]] = {}

    for person_id, player_name, first_name, family_name, display_name in rows:
        canonical_name = player_name or display_name
        if not canonical_name:
            continue

        player_payload = {
            "person_id": int(person_id),
            "player_name": str(canonical_name),
        }
        players.append(player_payload)

        alias_forms = {
            str(canonical_name),
            str(display_name) if display_name else "",
            " ".join(part for part in [first_name, family_name] if part),
        }
        single_token_candidates = [
            family_name,
            first_name,
        ]

        for alias_value in alias_forms:
            normalized_alias = _normalize_player_alias(alias_value)
            if not normalized_alias:
                continue
            alias_candidates.setdefault(normalized_alias, {})[int(person_id)] = player_payload

        for alias_value in single_token_candidates:
            normalized_alias = _normalize_player_alias(alias_value or "")
            if not normalized_alias:
                continue
            alias_candidates.setdefault(normalized_alias, {})[int(person_id)] = player_payload

    alias_index: dict[str, dict] = {}
    for alias_value, matches in sorted(alias_candidates.items()):
        ordered_matches = sorted(matches.values(), key=lambda player: player["player_name"])
        if len(ordered_matches) == 1:
            alias_index[alias_value] = {
                "status": "resolved",
                "player": ordered_matches[0],
            }
        else:
            alias_index[alias_value] = {
                "status": "ambiguous",
                "matches": ordered_matches,
            }

    return {
        "players": sorted(players, key=lambda player: player["player_name"]),
        "aliases": alias_index,
    }


def build_capability_artifact() -> dict:
    ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    inventory = json.loads(ATTRIBUTE_INVENTORY_PATH.read_text(encoding="utf-8"))
    contract = yaml.safe_load(EXECUTION_CONTRACT_PATH.read_text(encoding="utf-8"))
    planner_capabilities = _load_planner_derived_capabilities()

    objects = {obj["name"]: obj for obj in ontology["objects"]}
    inventory_objects = {table["object_name"] for table in inventory["tables"]}

    fact_objects: dict[str, dict] = {}
    for object_name, object_entry in objects.items():
        fact_objects[object_name] = {
            "description": object_entry["description"],
            "backing_table": object_entry["backing_table"],
            "public_attributes": _public_attribute_names(object_entry),
            "public_dimensions": _public_dimension_names(object_entry),
            "executable_metrics": _executable_metric_names(object_entry),
            "in_attribute_inventory": object_name in inventory_objects,
        }

    families: list[dict] = []
    for family in planner_capabilities["families"]:
        fact_object_name = family["core_fact_object"]
        _require(
            fact_object_name in fact_objects,
            f"Planner-derived family references unknown fact object '{fact_object_name}'.",
        )
        fact_object = fact_objects[fact_object_name]

        for metric_name in family["metrics"]:
            _require(
                metric_name in fact_object["executable_metrics"],
                f"Planner-derived metric '{metric_name}' is not executable on '{fact_object_name}'.",
            )

        row_object_name = family.get("row_object")
        if family["query_kind"] == "object_query":
            _require(
                row_object_name in fact_objects,
                f"Planner-derived family references unknown row object '{row_object_name}'.",
            )
            row_object = fact_objects[row_object_name]
            for dimension_name in family["dimensions"]:
                _require(
                    dimension_name in row_object["public_dimensions"],
                    f"Planner-derived dimension '{dimension_name}' is not public on '{row_object_name}'.",
                )

        for linked_filter in family["linked_filters"]:
            target_object_name = linked_filter["target_object"]
            _require(
                target_object_name in fact_objects,
                f"Planner-derived family references unknown linked filter object '{target_object_name}'.",
            )
            target_object = fact_objects[target_object_name]
            _require(
                linked_filter["attribute"] in target_object["public_dimensions"],
                f"Planner-derived linked filter attribute '{linked_filter['attribute']}' is not public on '{target_object_name}'.",
            )

        comparison_payload = dict(family["comparison"])
        if not comparison_payload["enabled"]:
            comparison_payload["entity_type"] = None
            comparison_payload["max_entities"] = None

        family_payload = {
            "family_key": family["family_key"],
            "query_kind": family["query_kind"],
            "core_fact_object": fact_object_name,
            "row_object": row_object_name,
            "metrics": sorted(family["metrics"]),
            "dimensions": list(family["dimensions"]),
            "required_filter_kinds": sorted(family["required_filter_kinds"]),
            "time_grain": family.get("time_grain"),
            "linked_filters": list(family["linked_filters"]),
            "allow_limit": bool(family["allow_limit"]),
            "require_order_by_metric": bool(family["require_order_by_metric"]),
            "comparison": comparison_payload,
        }
        families.append(family_payload)

    families.sort(
        key=lambda family: (
            family["query_kind"],
            family["core_fact_object"],
            family["row_object"] or "",
            ",".join(family["required_filter_kinds"]),
            family["time_grain"] or "",
            family["family_key"],
        )
    )

    allowed_filter_kinds = sorted(
        {
            filter_kind
            for family in families
            for filter_kind in family["required_filter_kinds"]
        }
    )
    allowed_time_grains = sorted(
        {
            family["time_grain"]
            for family in families
            if family["time_grain"] is not None
        }
    )
    top_level_query_kinds = sorted({family["query_kind"] for family in families})
    player_entity_index = _build_player_entity_index()

    artifact = {
        "version": contract["version"],
        "top_level_query_kinds": top_level_query_kinds,
        "allowed_filter_kinds": allowed_filter_kinds,
        "allowed_time_grains": allowed_time_grains,
        "allowed_assumptions": list(contract["allowed_assumptions"]),
        "fact_objects": fact_objects,
        "player_entity_index": player_entity_index,
        "families": families,
    }
    artifact["prompt_summary"] = _build_prompt_summary(families)
    return artifact


def write_capability_artifact() -> dict:
    artifact = build_capability_artifact()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return artifact


if __name__ == "__main__":
    write_capability_artifact()
