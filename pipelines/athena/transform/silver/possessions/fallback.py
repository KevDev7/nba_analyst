from __future__ import annotations

import re
from typing import Any

import build_silver_playbyplay_events as pbp_silver
from pbpstats_projection_common import InvalidNumberOfStartersException

from .exact import build_possession_rows_from_events

OPENING_CLOCK = "PT05M00.00S"
FAILED_PERIOD_RE = re.compile(r"Period:\s*(\d+)")


def parse_failed_period(exc: Exception) -> int | None:
    match = FAILED_PERIOD_RE.search(str(exc))
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def is_recoverable_reference_failure(exc: Exception) -> bool:
    if not isinstance(exc, InvalidNumberOfStartersException):
        return False
    failed_period = parse_failed_period(exc)
    return failed_period is not None and failed_period >= 5


def valid_closing_stint_for_period(
    on_court_rows: list[dict[str, Any]],
    period: int,
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in on_court_rows
        if pbp_silver.to_int_or_none(row.get("period")) == period
        and pbp_silver.to_int_or_none(row.get("lineup_valid_flag")) == 1
        and isinstance(row.get("home_personIds"), list)
        and isinstance(row.get("away_personIds"), list)
        and len(row.get("home_personIds") or []) == 5
        and len(row.get("away_personIds") or []) == 5
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: (
            pbp_silver.to_int_or_none(row.get("end_orderNumber")) or -1,
            pbp_silver.to_int_or_none(row.get("stint_id")) or -1,
        ),
    )


def row_has_complete_lineups(row: dict[str, Any]) -> bool:
    return (
        isinstance(row.get("home_personIds"), list)
        and isinstance(row.get("away_personIds"), list)
        and len(row.get("home_personIds") or []) == 5
        and len(row.get("away_personIds") or []) == 5
    )


def lineup_issue_tokens(row: dict[str, Any]) -> list[str]:
    issue = pbp_silver.null_if_empty(row.get("lineup_issue"))
    if issue is None:
        return []
    return [token.strip() for token in str(issue).split("|") if token.strip()]


def is_stale_sub_out_only_token(token: str) -> bool:
    return token.startswith("sub_out_not_in_lineup(")


def build_stale_sub_out_repaired_on_court_rows(
    on_court_rows: list[dict[str, Any]],
    *,
    failed_period: int,
) -> tuple[list[dict[str, Any]], bool] | None:
    failed_period_rows = [
        row for row in on_court_rows if pbp_silver.to_int_or_none(row.get("period")) == failed_period
    ]
    if not failed_period_rows:
        return None

    ordered_failed_rows = sorted(
        failed_period_rows,
        key=lambda row: (
            pbp_silver.to_int_or_none(row.get("start_orderNumber")) or 10**12,
            pbp_silver.to_int_or_none(row.get("stint_id")) or 10**12,
        ),
    )
    first_failed_period_row = ordered_failed_rows[0]
    if not row_has_complete_lineups(first_failed_period_row):
        return None

    any_invalid = False
    for row in ordered_failed_rows:
        if not row_has_complete_lineups(row):
            return None
        row_valid_flag = pbp_silver.to_int_or_none(row.get("lineup_valid_flag"))
        if row_valid_flag == 0:
            any_invalid = True
        tokens = lineup_issue_tokens(row)
        if not all(is_stale_sub_out_only_token(token) for token in tokens):
            return None

    if not any_invalid:
        return None

    effective_rows: list[dict[str, Any]] = []
    for row in on_court_rows:
        if pbp_silver.to_int_or_none(row.get("period")) != failed_period:
            effective_rows.append(row)
            continue
        updated = dict(row)
        updated["lineup_valid_flag"] = 1
        updated["lineup_issue"] = None
        effective_rows.append(updated)
    return effective_rows, False


def group_substitution_clusters(period_actions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    sorted_actions = sorted(
        period_actions,
        key=lambda action: (
            pbp_silver.to_int_or_none(action.get("orderNumber")) or 0,
            pbp_silver.to_int_or_none(action.get("actionNumber")) or 0,
        ),
    )
    clusters: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(sorted_actions):
        action = sorted_actions[index]
        if pbp_silver.normalized_action_type(action.get("actionType")) != "substitution":
            index += 1
            continue
        cluster = [action]
        cluster_clock = pbp_silver.null_if_empty(action.get("clock"))
        index += 1
        while index < len(sorted_actions):
            candidate = sorted_actions[index]
            if pbp_silver.normalized_action_type(candidate.get("actionType")) != "substitution":
                break
            if pbp_silver.null_if_empty(candidate.get("clock")) != cluster_clock:
                break
            cluster.append(candidate)
            index += 1
        clusters.append(cluster)
    return clusters


def apply_substitution_cluster(
    home_players: list[int],
    away_players: list[int],
    cluster: list[dict[str, Any]],
    *,
    home_team_id: int,
    away_team_id: int,
) -> tuple[list[int], list[int]] | None:
    current_home = set(home_players)
    current_away = set(away_players)

    for action in cluster:
        team_id = pbp_silver.to_int_or_none(action.get("teamId"))
        person_id = pbp_silver.to_int_or_none(action.get("personId"))
        sub_type = pbp_silver.null_if_empty(action.get("subType"))
        if team_id not in {home_team_id, away_team_id} or person_id is None or sub_type not in {"in", "out"}:
            return None
        target = current_home if team_id == home_team_id else current_away
        if sub_type == "out":
            if person_id not in target:
                return None
            target.remove(person_id)
        else:
            if person_id in target:
                return None
            target.add(person_id)

    if len(current_home) != 5 or len(current_away) != 5:
        return None
    return sorted(current_home), sorted(current_away)


def last_stint_for_period(
    on_court_rows: list[dict[str, Any]],
    period: int,
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in on_court_rows
        if pbp_silver.to_int_or_none(row.get("period")) == period
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: (
            pbp_silver.to_int_or_none(row.get("end_orderNumber")) or -1,
            pbp_silver.to_int_or_none(row.get("stint_id")) or -1,
        ),
    )


def normalize_person_ids(values: list[Any] | None) -> list[int]:
    return [
        player_id
        for player_id in (pbp_silver.to_int_or_none(value) for value in (values or []))
        if player_id is not None
    ]


def partial_side_flags(row: dict[str, Any]) -> tuple[bool, bool]:
    home_ids = normalize_person_ids(row.get("home_personIds"))
    away_ids = normalize_person_ids(row.get("away_personIds"))
    return len(home_ids) < 5, len(away_ids) < 5


def apply_side_substitutions(
    current_players: list[int],
    side_actions: list[dict[str, Any]],
) -> list[int] | None:
    current = list(current_players)
    for action in sorted(
        side_actions,
        key=lambda candidate: (
            pbp_silver.to_int_or_none(candidate.get("orderNumber")) or 0,
            pbp_silver.to_int_or_none(candidate.get("actionNumber")) or 0,
        ),
    ):
        person_id = pbp_silver.to_int_or_none(action.get("personId"))
        sub_type = pbp_silver.null_if_empty(action.get("subType"))
        if person_id is None or sub_type not in {"in", "out"}:
            return None
        if sub_type == "out":
            if person_id not in current:
                return None
            current.remove(person_id)
            continue
        if person_id in current:
            return None
        current.append(person_id)
    return sorted(current)


def reconcile_side_from_q4_drift(
    *,
    seed_players: list[int],
    drift_players: list[int],
    side_actions: list[dict[str, Any]],
) -> list[int] | None:
    reconciled = apply_side_substitutions(drift_players, side_actions)
    if reconciled is None:
        return None
    if len(reconciled) > 5:
        return None
    missing_slots = 5 - len(reconciled)
    if missing_slots < 0 or missing_slots > 1:
        return None
    missing_seed_players = [player_id for player_id in seed_players if player_id not in reconciled]
    if len(missing_seed_players) < missing_slots:
        return None
    reconciled.extend(missing_seed_players[:missing_slots])
    reconciled = sorted(dict.fromkeys(reconciled))
    if len(reconciled) != 5:
        return None
    return reconciled


def build_end_q4_drift_reconciled_on_court_rows(
    payload: dict[str, Any],
    on_court_rows: list[dict[str, Any]],
    *,
    failed_period: int,
) -> tuple[list[dict[str, Any]], bool] | None:
    if failed_period < 5:
        return None
    prior_valid_stint = valid_closing_stint_for_period(on_court_rows, failed_period - 1)
    prior_last_stint = last_stint_for_period(on_court_rows, failed_period - 1)
    if prior_valid_stint is None or prior_last_stint is None:
        return None

    failed_period_rows = [
        row for row in on_court_rows if pbp_silver.to_int_or_none(row.get("period")) == failed_period
    ]
    if not failed_period_rows:
        return None
    ordered_failed_rows = sorted(
        failed_period_rows,
        key=lambda row: (
            pbp_silver.to_int_or_none(row.get("start_orderNumber")) or 10**12,
            pbp_silver.to_int_or_none(row.get("stint_id")) or 10**12,
        ),
    )
    first_failed_row = ordered_failed_rows[0]
    if row_has_complete_lineups(first_failed_row):
        return None

    prior_partial_flags = partial_side_flags(prior_last_stint)
    first_partial_flags = partial_side_flags(first_failed_row)
    if not any(prior_partial_flags) or prior_partial_flags != first_partial_flags:
        return None

    game = payload.get("game") or {}
    all_actions = game.get("actions") or []
    period_actions = [
        action
        for action in all_actions
        if isinstance(action, dict)
        and pbp_silver.to_int_or_none(action.get("period")) == failed_period
    ]
    if not period_actions:
        return None
    opening_cluster = [
        action
        for action in sorted(
            period_actions,
            key=lambda action: (
                pbp_silver.to_int_or_none(action.get("orderNumber")) or 0,
                pbp_silver.to_int_or_none(action.get("actionNumber")) or 0,
            ),
        )
        if pbp_silver.normalized_action_type(action.get("actionType")) == "substitution"
        and pbp_silver.null_if_empty(action.get("clock")) == OPENING_CLOCK
    ]
    if not opening_cluster:
        return None

    home_team_id = pbp_silver.to_int_or_none(prior_valid_stint.get("home_teamId"))
    away_team_id = pbp_silver.to_int_or_none(prior_valid_stint.get("away_teamId"))
    if home_team_id is None or away_team_id is None:
        return None

    home_actions = [
        action
        for action in opening_cluster
        if pbp_silver.to_int_or_none(action.get("teamId")) == home_team_id
    ]
    away_actions = [
        action
        for action in opening_cluster
        if pbp_silver.to_int_or_none(action.get("teamId")) == away_team_id
    ]

    seed_home = normalize_person_ids(prior_valid_stint.get("home_personIds"))
    seed_away = normalize_person_ids(prior_valid_stint.get("away_personIds"))
    drift_home = normalize_person_ids(prior_last_stint.get("home_personIds"))
    drift_away = normalize_person_ids(prior_last_stint.get("away_personIds"))
    if len(seed_home) != 5 or len(seed_away) != 5:
        return None

    reconciled_home = reconcile_side_from_q4_drift(
        seed_players=seed_home,
        drift_players=drift_home,
        side_actions=home_actions,
    )
    reconciled_away = reconcile_side_from_q4_drift(
        seed_players=seed_away,
        drift_players=drift_away,
        side_actions=away_actions,
    )
    if reconciled_home is None or reconciled_away is None:
        return None

    start_order = pbp_silver.to_int_or_none(period_actions[0].get("orderNumber")) or 0
    start_clock = pbp_silver.null_if_empty(period_actions[0].get("clock"))
    end_order = pbp_silver.to_int_or_none(period_actions[-1].get("orderNumber")) or start_order
    rebuilt_rows = [
        row for row in on_court_rows if pbp_silver.to_int_or_none(row.get("period")) != failed_period
    ]
    rebuilt_rows.append(
        {
            "gameId": str(game.get("gameId") or "").zfill(10),
            "period": failed_period,
            "stint_id": 1,
            "start_orderNumber": start_order,
            "end_orderNumber": end_order,
            "start_clock": start_clock,
            "home_teamId": home_team_id,
            "away_teamId": away_team_id,
            "home_personIds": reconciled_home,
            "away_personIds": reconciled_away,
            "lineup_valid_flag": 1,
            "lineup_issue": None,
        }
    )
    return rebuilt_rows, True


def build_recovered_ot_stints(
    payload: dict[str, Any],
    *,
    failed_period: int,
    prior_stint: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool] | None:
    game = payload.get("game") or {}
    all_actions = game.get("actions") or []
    period_actions = [
        action
        for action in all_actions
        if isinstance(action, dict)
        and pbp_silver.to_int_or_none(action.get("period")) == failed_period
    ]
    if not period_actions:
        return None

    period_actions = sorted(
        period_actions,
        key=lambda action: (
            pbp_silver.to_int_or_none(action.get("orderNumber")) or 0,
            pbp_silver.to_int_or_none(action.get("actionNumber")) or 0,
        ),
    )
    home_team_id = pbp_silver.to_int_or_none(prior_stint.get("home_teamId"))
    away_team_id = pbp_silver.to_int_or_none(prior_stint.get("away_teamId"))
    prior_home = [
        player_id
        for player_id in (
            pbp_silver.to_int_or_none(value) for value in (prior_stint.get("home_personIds") or [])
        )
        if player_id is not None
    ]
    prior_away = [
        player_id
        for player_id in (
            pbp_silver.to_int_or_none(value) for value in (prior_stint.get("away_personIds") or [])
        )
        if player_id is not None
    ]
    if home_team_id is None or away_team_id is None or len(prior_home) != 5 or len(prior_away) != 5:
        return None

    clusters = group_substitution_clusters(period_actions)
    opening_cluster = clusters[0] if clusters and pbp_silver.null_if_empty(clusters[0][0].get("clock")) == OPENING_CLOCK else None

    current_home = list(prior_home)
    current_away = list(prior_away)
    opening_applied = False
    if opening_cluster:
        applied = apply_substitution_cluster(
            current_home,
            current_away,
            opening_cluster,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )
        if applied is None:
            return None
        current_home, current_away = applied
        opening_applied = True

    start_order = pbp_silver.to_int_or_none(period_actions[0].get("orderNumber")) or 0
    start_clock = pbp_silver.null_if_empty(period_actions[0].get("clock"))
    end_order = pbp_silver.to_int_or_none(period_actions[-1].get("orderNumber")) or start_order
    stints = [
        {
            "gameId": str(game.get("gameId") or "").zfill(10),
            "period": failed_period,
            "stint_id": 1,
            "start_orderNumber": start_order,
            "end_orderNumber": end_order,
            "start_clock": start_clock,
            "home_teamId": home_team_id,
            "away_teamId": away_team_id,
            "home_personIds": list(current_home),
            "away_personIds": list(current_away),
            "lineup_valid_flag": 1,
            "lineup_issue": None,
        }
    ]
    return stints, opening_applied


def build_effective_on_court_rows(
    payload: dict[str, Any],
    on_court_rows: list[dict[str, Any]],
    *,
    failed_period: int,
) -> tuple[list[dict[str, Any]], bool, str] | None:
    failed_period_rows = [
        row for row in on_court_rows if pbp_silver.to_int_or_none(row.get("period")) == failed_period
    ]
    first_failed_period_row = min(
        failed_period_rows,
        key=lambda row: (
            pbp_silver.to_int_or_none(row.get("start_orderNumber")) or 10**12,
            pbp_silver.to_int_or_none(row.get("stint_id")) or 10**12,
        ),
        default=None,
    )
    if first_failed_period_row is not None and pbp_silver.to_int_or_none(first_failed_period_row.get("lineup_valid_flag")) == 1:
        return on_court_rows, False, "fallback_ot_carry_forward"

    stale_repaired = build_stale_sub_out_repaired_on_court_rows(
        on_court_rows,
        failed_period=failed_period,
    )
    if stale_repaired is not None:
        effective_rows, opening_applied = stale_repaired
        return effective_rows, opening_applied, "fallback_ot_stale_sub_out_repair"

    end_q4_drift_repaired = build_end_q4_drift_reconciled_on_court_rows(
        payload,
        on_court_rows,
        failed_period=failed_period,
    )
    if end_q4_drift_repaired is not None:
        effective_rows, opening_applied = end_q4_drift_repaired
        return effective_rows, opening_applied, "fallback_ot_end_q4_drift_reconcile"

    prior_stint = valid_closing_stint_for_period(on_court_rows, failed_period - 1)
    if prior_stint is None:
        return None
    rebuilt = build_recovered_ot_stints(payload, failed_period=failed_period, prior_stint=prior_stint)
    if rebuilt is None:
        return None
    rebuilt_rows, opening_applied = rebuilt
    effective_rows = [
        row for row in on_court_rows if pbp_silver.to_int_or_none(row.get("period")) != failed_period
    ] + rebuilt_rows
    return effective_rows, opening_applied, "fallback_ot_carry_forward"


def annotate_fallback_rows(
    rows: list[dict[str, Any]],
    *,
    failed_period: int,
    opening_cluster_applied: bool,
    source_method: str,
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        updated["possessionSourceMethod"] = source_method
        updated["referenceFailureType"] = "InvalidNumberOfStartersException"
        updated["referenceFailurePeriod"] = failed_period
        updated["fallbackApplied"] = True
        updated["fallbackOpeningSubClusterApplied"] = opening_cluster_applied
        annotated.append(updated)
    return annotated


def build_fallback_rows_for_game(
    payload: dict[str, Any],
    playbyplay_rows: list[dict[str, Any]],
    on_court_rows: list[dict[str, Any]],
    *,
    reference_failure: Exception,
) -> tuple[list[dict[str, Any]], int, bool, str] | None:
    if not is_recoverable_reference_failure(reference_failure):
        return None
    failed_period = parse_failed_period(reference_failure)
    if failed_period is None:
        return None
    effective_on_court = build_effective_on_court_rows(payload, on_court_rows, failed_period=failed_period)
    if effective_on_court is None:
        return None
    effective_rows, opening_cluster_applied, source_method = effective_on_court
    fallback_rows = build_possession_rows_from_events(playbyplay_rows, on_court_rows=effective_rows)
    if not fallback_rows:
        return None
    return annotate_fallback_rows(
        fallback_rows,
        failed_period=failed_period,
        opening_cluster_applied=opening_cluster_applied,
        source_method=source_method,
    ), failed_period, opening_cluster_applied, source_method
