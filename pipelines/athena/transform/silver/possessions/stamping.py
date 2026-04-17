from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import build_silver_playbyplay_events as pbp_silver


def parse_time_actual_utc(value: Any) -> datetime | None:
    value = pbp_silver.null_if_empty(value)
    if value is None:
        return None

    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sort_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            pbp_silver.to_int_or_none(row.get("period")) or 0,
            pbp_silver.to_int_or_none(row.get("orderNumber")) or 0,
            pbp_silver.to_int_or_none(row.get("actionNumber")) or 0,
        ),
    )


def first_non_null(rows: list[dict[str, Any]], field: str) -> Any:
    for row in rows:
        value = row.get(field)
        if pbp_silver.null_if_empty(value) is not None:
            return value
    return None


def lineup_id_from_person_ids(person_ids: Any) -> str | None:
    if not isinstance(person_ids, list):
        return None
    normalized_ids = sorted(
        {
            str(player_id)
            for player_id in (pbp_silver.to_int_or_none(value) for value in person_ids)
            if player_id is not None
        }
    )
    if not normalized_ids:
        return None
    return "-".join(normalized_ids)


def sort_stints_for_stamping(stints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        stints,
        key=lambda stint: (
            pbp_silver.to_int_or_none(stint.get("start_orderNumber")) or 0,
            pbp_silver.to_int_or_none(stint.get("end_orderNumber")) or 0,
            pbp_silver.to_int_or_none(stint.get("stint_id")) or 0,
        ),
    )


def can_collapse_same_moment_stints(
    overlaps: list[dict[str, Any]],
    possession_start_clock: str | None,
) -> bool:
    if len(overlaps) <= 1 or possession_start_clock is None:
        return False
    overlap_start_clocks = {
        pbp_silver.null_if_empty(stint.get("start_clock"))
        for stint in overlaps
    }
    return overlap_start_clocks == {possession_start_clock}


def stamp_lineup_context(
    possession_rows: list[dict[str, Any]],
    on_court_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not possession_rows:
        return possession_rows

    on_court_by_period: dict[int | None, list[dict[str, Any]]] = {}
    for row in on_court_rows:
        period = pbp_silver.to_int_or_none(row.get("period"))
        on_court_by_period.setdefault(period, []).append(row)

    for possession in possession_rows:
        period = pbp_silver.to_int_or_none(possession.get("period"))
        start_order = pbp_silver.to_int_or_none(possession.get("startOrderNumber"))
        end_order = pbp_silver.to_int_or_none(possession.get("endOrderNumber"))
        overlaps: list[dict[str, Any]] = []
        for stint in on_court_by_period.get(period, []):
            stint_start = pbp_silver.to_int_or_none(stint.get("start_orderNumber"))
            stint_end = pbp_silver.to_int_or_none(stint.get("end_orderNumber"))
            if (
                start_order is None
                or end_order is None
                or stint_start is None
                or stint_end is None
            ):
                continue
            if not (stint_end <= start_order or stint_start > end_order):
                overlaps.append(stint)
        overlaps = sort_stints_for_stamping(overlaps)

        issues: list[str] = []
        home_lineup_ids = {
            lineup_id
            for lineup_id in (lineup_id_from_person_ids(stint.get("home_personIds")) for stint in overlaps)
            if lineup_id is not None
        }
        away_lineup_ids = {
            lineup_id
            for lineup_id in (lineup_id_from_person_ids(stint.get("away_personIds")) for stint in overlaps)
            if lineup_id is not None
        }
        home_lineup_id = next(iter(home_lineup_ids)) if len(home_lineup_ids) == 1 else None
        away_lineup_id = next(iter(away_lineup_ids)) if len(away_lineup_ids) == 1 else None
        collapsed_same_moment = can_collapse_same_moment_stints(
            overlaps,
            pbp_silver.null_if_empty(possession.get("startClock")),
        )
        if collapsed_same_moment:
            final_stint = overlaps[-1]
            home_lineup_id = lineup_id_from_person_ids(final_stint.get("home_personIds"))
            away_lineup_id = lineup_id_from_person_ids(final_stint.get("away_personIds"))

        if not overlaps:
            issues.append("missing_on_court_coverage")
        if len(home_lineup_ids) > 1 and not collapsed_same_moment:
            issues.append(f"multiple_home_lineups(count={len(home_lineup_ids)})")
        if len(away_lineup_ids) > 1 and not collapsed_same_moment:
            issues.append(f"multiple_away_lineups(count={len(away_lineup_ids)})")

        overlap_invalid_issues = [
            pbp_silver.null_if_empty(stint.get("lineup_issue"))
            for stint in overlaps
            if pbp_silver.to_int_or_none(stint.get("lineup_valid_flag")) == 0
        ]
        if overlap_invalid_issues:
            issues.append("overlapping_invalid_stint")
            issues.extend(str(issue) for issue in overlap_invalid_issues if issue is not None)

        possession["homeLineupId"] = home_lineup_id
        possession["awayLineupId"] = away_lineup_id
        possession["lineupValidFlag"] = int(len(issues) == 0)
        possession["lineupIssue"] = " | ".join(dict.fromkeys(issues)) if issues else None

    return possession_rows
