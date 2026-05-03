#!/usr/bin/env python3
# Purpose:
# Audit whether public measure columns are ready to be exposed as semantic metrics.
#
# Uses:
# - pipelines/athena/metadata/semantic_gold_attribute_inventory.json
# - fixtures/ontology/semantic-gold.yaml
# - fixtures/duckdb/gold_slice.duckdb
#
# Produces:
# - a markdown or JSON report showing exposed, deferred, missing, and unexpected
#   metric-quality states by ontology object.

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_semantic_ontology import (  # noqa: E402
    ATTRIBUTE_INVENTORY_PATH,
    ONTOLOGY_OUTPUT_PATH,
    is_public_measure_column,
    metric_column_is_exposure_ready,
    quote_identifier,
)
from scripts.load_gold_snapshot import load_database  # noqa: E402


DEFAULT_OBJECTS = ("TeamGame", "TeamSeason")


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def load_inventory() -> dict[str, Any]:
    return json.loads(ATTRIBUTE_INVENTORY_PATH.read_text(encoding="utf-8"))


def load_ontology() -> dict[str, Any]:
    return yaml.safe_load(ONTOLOGY_OUTPUT_PATH.read_text(encoding="utf-8"))


def public_measure_columns(table_entry: dict[str, Any]) -> list[str]:
    return [
        str(column["name"])
        for column in table_entry["columns"]
        if is_public_measure_column(column)
    ]


def metric_source_columns(ontology_object: dict[str, Any]) -> set[str]:
    measure_attributes = {
        str(attribute["name"])
        for attribute in ontology_object["attributes"]
        if attribute["kind"] == "measure" and attribute["visibility"] == "public"
    }
    sources: set[str] = set()
    for metric in ontology_object.get("metrics", []):
        for source_attribute in metric.get("source_attributes", []):
            if str(source_attribute) in measure_attributes:
                sources.add(str(source_attribute))
    return sources


def metric_names_by_source(ontology_object: dict[str, Any]) -> dict[str, list[str]]:
    measure_attributes = {
        str(attribute["name"])
        for attribute in ontology_object["attributes"]
        if attribute["kind"] == "measure" and attribute["visibility"] == "public"
    }
    by_source: dict[str, list[str]] = {attribute: [] for attribute in measure_attributes}
    for metric in ontology_object.get("metrics", []):
        for source_attribute in metric.get("source_attributes", []):
            source = str(source_attribute)
            if source in by_source:
                by_source[source].append(str(metric["name"]))
    return by_source


def profile_measure_columns(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    columns: list[str],
) -> tuple[int, dict[str, dict[str, Any]]]:
    row_count = int(
        conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table_name)}").fetchone()[0]
    )
    if not columns:
        return row_count, {}

    expressions: list[str] = []
    for column in columns:
        quoted_column = quote_identifier(column)
        expressions.extend(
            [
                f"COUNT({quoted_column}) AS {quote_identifier(column + '__non_null_count')}",
                f"MIN({quoted_column}) AS {quote_identifier(column + '__min')}",
                f"MAX({quoted_column}) AS {quote_identifier(column + '__max')}",
            ]
        )

    row = conn.execute(
        f"SELECT {', '.join(expressions)} FROM {quote_identifier(table_name)}"
    ).fetchone()
    values = list(row or [])
    profiles: dict[str, dict[str, Any]] = {}
    for index, column in enumerate(columns):
        non_null_count = int(values[index * 3] or 0)
        min_value = values[index * 3 + 1]
        max_value = values[index * 3 + 2]
        profiles[column] = {
            "non_null_count": non_null_count,
            "min": json_safe(min_value),
            "max": json_safe(max_value),
            "is_populated": non_null_count > 0 and not (min_value == 0 and max_value == 0),
        }
    return row_count, profiles


def metric_quality_reason(object_name: str, column: str, status: str) -> str:
    if status == "missing_data":
        return "Column is all null or constant zero in the current DuckDB snapshot."
    if status == "deferred_quality":
        return (
            "Remaining TeamGame percentage metrics need exact scale/formula audit "
            "before ontology exposure."
        )
    if status == "unexpected_unexposed":
        return "Column appears populated and exposure-ready but is not used by any ontology metric."
    return "Column is populated and exposed through ontology metrics."


def classify_column(
    *,
    object_name: str,
    column: str,
    profile: dict[str, Any],
    exposed_sources: set[str],
) -> str:
    if not profile["is_populated"]:
        return "missing_data"
    if column in exposed_sources:
        return "exposed"
    if metric_column_is_exposure_ready(object_name, column):
        return "unexpected_unexposed"
    return "deferred_quality"


def audit_metric_quality(
    *,
    objects: list[str] | tuple[str, ...] = DEFAULT_OBJECTS,
    database_path: Path | None = None,
) -> dict[str, Any]:
    inventory = load_inventory()
    ontology = load_ontology()
    table_by_object = {str(table["object_name"]): table for table in inventory["tables"]}
    ontology_by_object = {str(obj["name"]): obj for obj in ontology["objects"]}
    db_path = database_path or load_database()

    audited_objects: dict[str, Any] = {}
    with duckdb.connect(str(db_path), read_only=True) as conn:
        for object_name in objects:
            table_entry = table_by_object[object_name]
            ontology_object = ontology_by_object[object_name]
            columns = public_measure_columns(table_entry)
            row_count, profiles = profile_measure_columns(
                conn,
                str(table_entry["table_name"]),
                columns,
            )
            exposed_sources = metric_source_columns(ontology_object)
            names_by_source = metric_names_by_source(ontology_object)
            audited_columns = []
            for column in columns:
                status = classify_column(
                    object_name=object_name,
                    column=column,
                    profile=profiles[column],
                    exposed_sources=exposed_sources,
                )
                audited_columns.append(
                    {
                        "column": column,
                        "status": status,
                        "reason": metric_quality_reason(object_name, column, status),
                        "non_null_count": profiles[column]["non_null_count"],
                        "min": profiles[column]["min"],
                        "max": profiles[column]["max"],
                        "metrics": names_by_source.get(column, []),
                    }
                )

            counts = Counter(column["status"] for column in audited_columns)
            audited_objects[object_name] = {
                "table": table_entry["table_name"],
                "row_count": row_count,
                "public_measure_columns": len(columns),
                "counts": {
                    "exposed": counts["exposed"],
                    "deferred_quality": counts["deferred_quality"],
                    "missing_data": counts["missing_data"],
                    "unexpected_unexposed": counts["unexpected_unexposed"],
                },
                "columns": audited_columns,
            }

    return {
        "database_path": str(db_path),
        "objects": audited_objects,
    }


def columns_with_status(object_audit: dict[str, Any], status: str) -> list[dict[str, Any]]:
    return [column for column in object_audit["columns"] if column["status"] == status]


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Semantic Metric Quality Audit",
        "",
        f"DuckDB snapshot: `{audit['database_path']}`",
        "",
    ]
    for object_name, object_audit in audit["objects"].items():
        counts = object_audit["counts"]
        lines.extend(
            [
                f"## {object_name}",
                "",
                f"- table: `{object_audit['table']}`",
                f"- rows: {object_audit['row_count']}",
                f"- public measure columns: {object_audit['public_measure_columns']}",
                f"- exposed: {counts['exposed']}",
                f"- deferred for quality audit: {counts['deferred_quality']}",
                f"- missing data: {counts['missing_data']}",
                f"- unexpected unexposed: {counts['unexpected_unexposed']}",
                "",
            ]
        )
        for status, heading in (
            ("unexpected_unexposed", "Unexpected Unexposed Columns"),
            ("missing_data", "Missing Data Columns"),
            ("deferred_quality", "Deferred Quality Columns"),
        ):
            columns = columns_with_status(object_audit, status)
            if not columns:
                continue
            lines.extend(
                [
                    f"### {heading}",
                    "",
                    "| Column | Non-null | Min | Max | Reason |",
                    "| --- | ---: | --- | --- | --- |",
                ]
            )
            for column in columns:
                lines.append(
                    "| {column} | {non_null_count} | {min} | {max} | {reason} |".format(
                        **column
                    )
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit semantic-gold measure columns against ontology metric exposure."
    )
    parser.add_argument(
        "--object",
        dest="objects",
        action="append",
        choices=DEFAULT_OBJECTS,
        help="Ontology object to audit. May be passed more than once. Defaults to TeamGame and TeamSeason.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--fail-on-unexpected",
        action="store_true",
        help="Exit non-zero if any populated exposure-ready measure is not exposed as a metric.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audit = audit_metric_quality(objects=args.objects or DEFAULT_OBJECTS)
    if args.format == "json":
        print(json.dumps(audit, indent=2, sort_keys=True))
    else:
        print(render_markdown(audit), end="")

    unexpected_count = sum(
        object_audit["counts"]["unexpected_unexposed"]
        for object_audit in audit["objects"].values()
    )
    if args.fail_on_unexpected and unexpected_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
