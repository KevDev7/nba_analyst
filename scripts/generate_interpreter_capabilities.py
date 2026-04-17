#!/usr/bin/env python3
# Purpose:
# Generate the canonical interpreter capability artifact from ontology metadata
# plus the temporary execution capability contract.
#
# Uses:
# - fixtures/ontology/semantic-gold.yaml
# - pipelines/athena/metadata/semantic_gold_attribute_inventory.json
# - pipelines/athena/metadata/semantic_interpreter_execution_contract.yaml
#
# Produces:
# - fixtures/interpreter/semantic-capabilities.json
#
# Next:
# - apps/cli/semantic_interpreter.py

from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
ATTRIBUTE_INVENTORY_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_attribute_inventory.json"
)
EXECUTION_CONTRACT_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_interpreter_execution_contract.yaml"
)
OUTPUT_PATH = ROOT / "fixtures" / "interpreter" / "semantic-capabilities.json"


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


def _build_prompt_summary(families: list[dict]) -> str:
    lines = [
        "Supported semantic families (generated from ontology + execution contract):"
    ]
    for family in families:
        dimension_text = ", ".join(family["dimensions"]) if family["dimensions"] else "no business grouping dimension"
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
            f"- {family['family_key']}: {family['query_kind']} on {family['core_fact_object']} with metrics [{metric_text}], "
            f"dimensions [{dimension_text}], required filters [{filter_text}]{row_text}{time_text}{linked_text}{comparison_text}"
        )
    return "\n".join(lines)


def build_capability_artifact() -> dict:
    ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    inventory = json.loads(ATTRIBUTE_INVENTORY_PATH.read_text(encoding="utf-8"))
    contract = yaml.safe_load(EXECUTION_CONTRACT_PATH.read_text(encoding="utf-8"))

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
    for family in contract["families"]:
        fact_object_name = family["core_fact_object"]
        _require(
            fact_object_name in fact_objects,
            f"Execution contract references unknown fact object '{fact_object_name}'.",
        )
        fact_object = fact_objects[fact_object_name]

        for metric_name in family["metrics"]:
            _require(
                metric_name in fact_object["executable_metrics"],
                f"Execution contract metric '{metric_name}' is not executable on '{fact_object_name}'.",
            )

        if family["query_kind"] == "object_query":
            row_object_name = family["row_object"]
            _require(
                row_object_name in fact_objects,
                f"Execution contract references unknown row object '{row_object_name}'.",
            )
            row_object = fact_objects[row_object_name]
            for dimension_name in family["dimensions"]:
                _require(
                    dimension_name in row_object["public_dimensions"],
                    f"Execution contract dimension '{dimension_name}' is not public on '{row_object_name}'.",
                )
        else:
            row_object_name = family.get("row_object")
            row_object = fact_objects.get(row_object_name) if row_object_name else None

        for linked_filter in family["linked_filters"]:
            target_object_name = linked_filter["target_object"]
            _require(
                target_object_name in fact_objects,
                f"Execution contract references unknown linked filter object '{target_object_name}'.",
            )
            target_object = fact_objects[target_object_name]
            _require(
                linked_filter["attribute"] in target_object["public_dimensions"],
                f"Execution contract linked filter attribute '{linked_filter['attribute']}' is not public on '{target_object_name}'.",
            )

        family_payload = {
            "family_key": family["family_key"],
            "query_kind": family["query_kind"],
            "core_fact_object": fact_object_name,
            "row_object": family.get("row_object"),
            "metrics": list(family["metrics"]),
            "dimensions": list(family["dimensions"]),
            "required_filter_kinds": list(family["required_filter_kinds"]),
            "time_grain": family.get("time_grain"),
            "linked_filters": list(family["linked_filters"]),
            "allow_limit": bool(family["allow_limit"]),
            "require_order_by_metric": bool(family["require_order_by_metric"]),
            "comparison": family["comparison"],
        }
        families.append(family_payload)

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

    artifact = {
        "version": contract["version"],
        "top_level_query_kinds": top_level_query_kinds,
        "allowed_filter_kinds": allowed_filter_kinds,
        "allowed_time_grains": allowed_time_grains,
        "allowed_assumptions": list(contract["allowed_assumptions"]),
        "comparison_entities": list(contract["comparison_entities"]),
        "fact_objects": fact_objects,
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
