from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


def build_scd2_versions(
    *,
    events: list[dict[str, Any]],
    entity_id_col: str,
    tracked_cols: list[str],
    event_time_col: str,
    event_date_col: str | None = None,
    event_order_cols: list[str] | None = None,
    record_source: str | None = None,
    carry_forward_cols: list[str] | None = None,
) -> list[dict[str, Any]]:
    carry_forward = set(carry_forward_cols or [])
    sort_cols = event_order_cols or [event_time_col]
    far_future = datetime.max.replace(tzinfo=timezone.utc)

    grouped_events: dict[Any, list[dict[str, Any]]] = {}
    for event in events:
        entity_id = event.get(entity_id_col)
        if entity_id is None:
            continue
        grouped_events.setdefault(entity_id, []).append(dict(event))

    versions: list[dict[str, Any]] = []
    for entity_id in sorted(grouped_events, key=lambda value: (value is None, value)):
        entity_events = grouped_events[entity_id]
        entity_events.sort(
            key=lambda row: tuple(
                (
                    row.get(col) is None,
                    row.get(col) if row.get(col) is not None else far_future if col == event_time_col else "",
                )
                for col in sort_cols
            )
        )

        seen_dates = [
            event.get(event_date_col)
            for event in entity_events
            if event_date_col and event.get(event_date_col) is not None
        ]
        first_seen = min(seen_dates) if seen_dates else None
        last_seen = max(seen_dates) if seen_dates else None

        carried: dict[str, Any] = {col: None for col in carry_forward}
        current_state: tuple[Any, ...] | None = None
        current_version: dict[str, Any] | None = None

        for event in entity_events:
            effective_values: dict[str, Any] = {}
            for col in tracked_cols:
                raw_value = event.get(col)
                if raw_value is not None:
                    effective_values[col] = raw_value
                    if col in carry_forward:
                        carried[col] = raw_value
                elif col in carry_forward:
                    effective_values[col] = carried[col]
                else:
                    effective_values[col] = None

            event_state = tuple(effective_values[col] for col in tracked_cols)
            event_time = event.get(event_time_col)

            if current_version is None:
                current_state = event_state
                current_version = {
                    entity_id_col: entity_id,
                    "valid_from_utc": event_time,
                    "valid_to_utc": None,
                    "is_current": 1,
                    "first_seen_game_date": first_seen,
                    "last_seen_game_date": last_seen,
                    "record_source": record_source,
                    **effective_values,
                }
                continue

            if event_state == current_state:
                if current_version["valid_from_utc"] is None and event_time is not None:
                    current_version["valid_from_utc"] = event_time
                continue

            close_scd2_version(current_version, event_time)
            versions.append(current_version)
            current_state = event_state
            current_version = {
                entity_id_col: entity_id,
                "valid_from_utc": event_time,
                "valid_to_utc": None,
                "is_current": 1,
                "first_seen_game_date": first_seen,
                "last_seen_game_date": last_seen,
                "record_source": record_source,
                **effective_values,
            }

        if current_version is not None:
            versions.append(current_version)

    return versions


def close_scd2_version(version_row: dict[str, Any], next_start: datetime | None) -> None:
    valid_from = version_row.get("valid_from_utc")
    valid_to = None
    if next_start is not None and valid_from is not None:
        if next_start > valid_from:
            valid_to = next_start - timedelta(microseconds=1)
        else:
            valid_to = next_start
    version_row["valid_to_utc"] = valid_to
    version_row["is_current"] = 0


def assign_surrogate_keys(
    rows: list[dict[str, Any]],
    *,
    sk_col: str,
    sort_keys: list[str],
) -> list[dict[str, Any]]:
    far_future = datetime.max.replace(tzinfo=timezone.utc)

    def sort_tuple(row: dict[str, Any]) -> tuple[Any, ...]:
        output: list[Any] = []
        for key in sort_keys:
            value = row.get(key)
            if isinstance(value, datetime):
                output.extend((value is None, value if value is not None else far_future))
            else:
                output.extend((value is None, value if value is not None else ""))
        return tuple(output)

    ordered = sorted(rows, key=sort_tuple)
    for index, row in enumerate(ordered, start=1):
        row[sk_col] = index
    return ordered


def resolve_scd2_sk(
    *,
    fact_rows: list[dict[str, Any]],
    dim_rows: list[dict[str, Any]],
    natural_id_col: str,
    fact_event_time_col: str,
    sk_col: str,
    output_sk_col: str,
    fact_natural_id_col: str | None = None,
) -> list[dict[str, Any]]:
    fact_natural_id_col = fact_natural_id_col or natural_id_col
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for row in dim_rows:
        natural_id = row.get(natural_id_col)
        if natural_id is None:
            continue
        grouped.setdefault(natural_id, []).append(row)

    for rows in grouped.values():
        rows.sort(
            key=lambda row: (
                row.get("valid_from_utc") is None,
                row.get("valid_from_utc") or datetime.max.replace(tzinfo=timezone.utc),
                row.get(sk_col) is None,
                row.get(sk_col) or 0,
            )
        )

    resolved: list[dict[str, Any]] = []
    for fact_row in fact_rows:
        row = dict(fact_row)
        natural_id = row.get(fact_natural_id_col)
        event_time = row.get(fact_event_time_col)
        resolved_sk = None
        candidates = grouped.get(natural_id, [])
        if event_time is not None:
            matching = [
                candidate
                for candidate in candidates
                if (
                    (candidate.get("valid_from_utc") is None or candidate.get("valid_from_utc") <= event_time)
                    and (candidate.get("valid_to_utc") is None or event_time <= candidate.get("valid_to_utc"))
                )
            ]
            if matching:
                matching.sort(
                    key=lambda candidate: (
                        candidate.get("valid_from_utc") is None,
                        candidate.get("valid_from_utc") or datetime.min.replace(tzinfo=timezone.utc),
                        candidate.get("is_current") != 1,
                        candidate.get(sk_col) is None,
                        candidate.get(sk_col) or 0,
                    )
                )
                resolved_sk = matching[-1].get(sk_col)

            if resolved_sk is None:
                past = [
                    candidate
                    for candidate in candidates
                    if candidate.get("valid_from_utc") is not None and candidate.get("valid_from_utc") <= event_time
                ]
                if past:
                    past.sort(
                        key=lambda candidate: (
                            candidate.get("valid_from_utc") is None,
                            candidate.get("valid_from_utc") or datetime.min.replace(tzinfo=timezone.utc),
                            candidate.get(sk_col) is None,
                            candidate.get(sk_col) or 0,
                        )
                    )
                    resolved_sk = past[-1].get(sk_col)

            if resolved_sk is None:
                future = [
                    candidate
                    for candidate in candidates
                    if candidate.get("valid_from_utc") is not None and candidate.get("valid_from_utc") > event_time
                ]
                if future:
                    future.sort(
                        key=lambda candidate: (
                            candidate.get("valid_from_utc") is None,
                            candidate.get("valid_from_utc") or datetime.max.replace(tzinfo=timezone.utc),
                            candidate.get(sk_col) is None,
                            candidate.get(sk_col) or 0,
                        )
                    )
                    resolved_sk = future[0].get(sk_col)

        if resolved_sk is None:
            current = [candidate for candidate in candidates if candidate.get("is_current") == 1]
            if current:
                current.sort(
                    key=lambda candidate: (
                        candidate.get("valid_from_utc") is None,
                        candidate.get("valid_from_utc") or datetime.min.replace(tzinfo=timezone.utc),
                        candidate.get(sk_col) is None,
                        candidate.get(sk_col) or 0,
                    )
                )
                resolved_sk = current[-1].get(sk_col)

        if resolved_sk is None and candidates:
            resolved_sk = candidates[-1].get(sk_col)
        row[output_sk_col] = resolved_sk
        resolved.append(row)

    return resolved
