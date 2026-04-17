from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Literal

import duckdb
import pyarrow as pa

from .gold_transform_helpers import to_float_or_none


PercentileDirection = Literal["higher", "lower"]
PercentileQualifier = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class PercentileMetricSpec:
    source_field: str
    output_field: str
    direction: PercentileDirection
    qualifies: PercentileQualifier


def register_arrow_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    table: pa.Table,
) -> None:
    temp_name = f"__{table_name}_arrow"
    conn.register(temp_name, table)
    conn.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM "{temp_name}"')
    conn.unregister(temp_name)


def attach_percentiles(
    rows: list[dict[str, Any]],
    *,
    metric_specs: list[PercentileMetricSpec],
    group_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    grouped_rows: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for spec in metric_specs:
            row.setdefault(spec.output_field, None)
        group_key = tuple(row.get(field) for field in group_fields)
        grouped_rows[group_key].append(row)

    for group_rows in grouped_rows.values():
        for spec in metric_specs:
            eligible_rows: list[tuple[dict[str, Any], float]] = []
            for row in group_rows:
                metric_value = to_float_or_none(row.get(spec.source_field))
                if metric_value is None or not spec.qualifies(row):
                    continue
                eligible_rows.append((row, metric_value))

            if not eligible_rows:
                continue
            if len(eligible_rows) == 1:
                eligible_rows[0][0][spec.output_field] = 100
                continue

            ordered_values = sorted(
                (metric_value for _, metric_value in eligible_rows),
                reverse=spec.direction == "lower",
            )
            max_rank_by_value: dict[float, int] = {}
            for rank, metric_value in enumerate(ordered_values, start=1):
                max_rank_by_value[metric_value] = rank

            denominator = len(eligible_rows) - 1
            for row, metric_value in eligible_rows:
                max_rank = max_rank_by_value[metric_value]
                percentile = round(((max_rank - 1) / denominator) * 100)
                row[spec.output_field] = max(0, min(100, int(percentile)))

    return rows
