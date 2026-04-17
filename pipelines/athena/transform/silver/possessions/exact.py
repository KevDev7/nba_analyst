from __future__ import annotations

from typing import Any

import build_silver_playbyplay_events as pbp_silver
from pbpstats.resources.enhanced_pbp import (
    FieldGoal,
    FreeThrow,
    JumpBall,
    Rebound,
    Substitution,
    Timeout,
    Turnover,
)
from pbpstats.resources.possessions.possession import Possession
from pbpstats_projection_common import load_live_possession_items

from .stamping import first_non_null, parse_time_actual_utc, sort_event_rows, stamp_lineup_context

EXACT_TARGET_COLUMNS = [
    "gameId",
    "possessionNumber",
    "possessionNumberInPeriod",
    "period",
    "startActionNumber",
    "endActionNumber",
    "startOrderNumber",
    "endOrderNumber",
    "startClock",
    "endClock",
    "startTimeActualUtc",
    "endTimeActualUtc",
    "secondsElapsed",
    "offenseTeamId",
    "defenseTeamId",
    "offenseHomeAway",
    "defenseHomeAway",
    "startScoreMargin",
    "endScoreMargin",
    "pointsScoredOnPossession",
    "possessionStartType",
    "possessionEndType",
    "possessionBoundaryReason",
    "possessionHasTimeout",
    "previousPossessionHasTimeout",
    "isSecondChancePossession",
    "isPenaltyPossession",
    "countsAsPossession",
    "previousPossessionNumber",
    "nextPossessionNumber",
    "previousPossessionEndingActionNumber",
    "homeLineupId",
    "awayLineupId",
    "lineupValidFlag",
    "lineupIssue",
    "fieldGoalAttempts",
    "freeThrowAttempts",
    "turnovers",
    "offensiveRebounds",
    "madeFieldGoals",
]


def build_playbyplay_lookup(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    for row in rows:
        action_number = pbp_silver.to_int_or_none(row.get("actionNumber"))
        if action_number is not None:
            lookup[action_number] = row
    return lookup


def other_team_id(team_id: int | None, known_team_ids: list[int]) -> int | None:
    if team_id is None:
        return None
    for candidate in known_team_ids:
        if candidate != team_id:
            return candidate
    return None


def possession_event_row_lookup(
    possession: Possession,
    playbyplay_lookup: dict[int, dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
    first_event = possession.events[0] if possession.events else None
    ending_event = possession_ending_event(possession.events) if possession.events else None
    previous_ending_event = (
        possession_ending_event(possession.previous_possession.events)
        if getattr(possession, "previous_possession", None) is not None
        else None
    )
    first_row = (
        None
        if first_event is None
        else playbyplay_lookup.get(pbp_silver.to_int_or_none(getattr(first_event, "event_num", None)) or -1)
    )
    ending_row = (
        None
        if ending_event is None
        else playbyplay_lookup.get(pbp_silver.to_int_or_none(getattr(ending_event, "event_num", None)) or -1)
    )
    previous_ending_row = (
        None
        if previous_ending_event is None
        else playbyplay_lookup.get(pbp_silver.to_int_or_none(getattr(previous_ending_event, "event_num", None)) or -1)
    )
    return first_row, ending_row, previous_ending_row


def score_points_for_location(score_home: Any, score_away: Any, location: Any) -> int | None:
    home = pbp_silver.to_int_or_none(score_home)
    away = pbp_silver.to_int_or_none(score_away)
    location_text = pbp_silver.null_if_empty(location)
    if home is None or away is None or location_text is None:
        return None
    return home if str(location_text) == "h" else away if str(location_text) == "v" else None


def score_margin_from_score_dict(
    offense_team_id: int | None,
    score: dict[Any, Any],
) -> int | None:
    if offense_team_id is None:
        return None
    offense_points = int(score.get(offense_team_id, 0))
    defense_points = None
    for team_id, points in score.items():
        if team_id != offense_team_id:
            defense_points = points
            break
    return offense_points - int(defense_points or 0)


def ending_event_row(possession_events: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(possession_events):
        if pbp_silver.to_bool_or_none(row.get("isPossessionEndingEvent")):
            return row
    return possession_events[-1]


def possession_ending_event(events: list[Any]) -> Any:
    for event in reversed(events):
        if bool(getattr(event, "is_possession_ending_event", False)):
            return event
    return last_non_substitution_event(events)


def last_non_substitution_row(possession_events: list[dict[str, Any]]) -> dict[str, Any]:
    for row in reversed(possession_events):
        if not pbp_silver.to_bool_or_none(row.get("isSubstitution")):
            return row
    return possession_events[-1]


def last_non_substitution_event(events: list[Any]) -> Any:
    for event in reversed(events):
        if not isinstance(event, Substitution):
            return event
    return events[-1]


def linked_shot_row(
    possession_events: list[dict[str, Any]],
    rebound_row: dict[str, Any],
) -> dict[str, Any] | None:
    shot_action_number = pbp_silver.to_int_or_none(rebound_row.get("shotActionNumber"))
    if shot_action_number is None:
        return None
    for row in reversed(possession_events):
        if pbp_silver.to_int_or_none(row.get("actionNumber")) == shot_action_number:
            return row
    return None


def is_real_rebound_event(possession_events: list[dict[str, Any]], index: int) -> bool:
    action_lookup = {
        (event.get("gameId"), pbp_silver.to_int_or_none(event.get("actionNumber"))): event
        for event in possession_events
        if pbp_silver.to_int_or_none(event.get("actionNumber")) is not None
    }
    return pbp_silver.rebound_is_real(possession_events, index, action_lookup)


def possession_timeout_flag(possession_events: list[dict[str, Any]], end_clock: Any) -> bool:
    for index, row in enumerate(possession_events):
        if not pbp_silver.to_bool_or_none(row.get("isTimeout")):
            continue
        timeout_clock = pbp_silver.null_if_empty(row.get("clock"))
        if timeout_clock != pbp_silver.null_if_empty(end_clock):
            next_row = possession_events[index + 1] if index + 1 < len(possession_events) else None
            if (
                next_row is not None
                and pbp_silver.to_bool_or_none(next_row.get("isFreeThrow"))
                and not pbp_silver.to_bool_or_none(next_row.get("isTechnicalFt"))
                and pbp_silver.null_if_empty(next_row.get("clock")) == timeout_clock
            ):
                continue
            return True

        for later_row in possession_events[index + 1 :]:
            if (
                pbp_silver.to_bool_or_none(later_row.get("isTurnover"))
                and pbp_silver.null_if_empty(later_row.get("clock")) == timeout_clock
            ):
                return True
    return False


def previous_possession_timeout_flag(
    previous_events: list[dict[str, Any]] | None,
    current_start_clock: Any,
) -> bool:
    if not previous_events:
        return False
    start_clock = pbp_silver.null_if_empty(current_start_clock)
    for index, row in enumerate(previous_events):
        if not pbp_silver.to_bool_or_none(row.get("isTimeout")):
            continue
        if pbp_silver.null_if_empty(row.get("clock")) != start_clock:
            continue
        next_row = previous_events[index + 1] if index + 1 < len(previous_events) else None
        if (
            next_row is not None
            and pbp_silver.to_bool_or_none(next_row.get("isFreeThrow"))
            and pbp_silver.null_if_empty(next_row.get("clock")) == start_clock
        ):
            continue
        return True
    return False


def possession_start_type_from_previous(
    previous_events: list[dict[str, Any]] | None,
    possession_has_timeout: bool,
    previous_possession_has_timeout: bool,
) -> str:
    if not previous_events:
        return "off_deadball"
    if possession_has_timeout or previous_possession_has_timeout:
        return "off_timeout"

    previous_end = last_non_substitution_row(previous_events)
    if pbp_silver.to_bool_or_none(previous_end.get("isFreeThrow")):
        shot_result = pbp_silver.null_if_empty(previous_end.get("shotResult"))
        if shot_result is not None and str(shot_result).strip().lower() == "made":
            return "off_ft_make"
    if pbp_silver.to_bool_or_none(previous_end.get("isMadeShot")):
        if pbp_silver.to_bool_or_none(previous_end.get("isFreeThrow")):
            return "off_ft_make"
        return "off_3pt_make" if pbp_silver.to_int_or_none(previous_end.get("shotValue")) == 3 else "off_2pt_make"

    if pbp_silver.to_bool_or_none(previous_end.get("isTurnover")):
        return (
            "off_live_ball_turnover"
            if pbp_silver.to_int_or_none(previous_end.get("stealPersonId")) is not None
            else "off_deadball"
        )

    if pbp_silver.to_bool_or_none(previous_end.get("isRebound")):
        if pbp_silver.to_int_or_none(previous_end.get("personId")) in {None, 0}:
            return "off_deadball"
        shot_row = linked_shot_row(previous_events, previous_end)
        if shot_row is not None and pbp_silver.to_bool_or_none(shot_row.get("isFreeThrow")):
            return "off_ft_miss"
        shot_value = pbp_silver.to_int_or_none(previous_end.get("shotValue"))
        if shot_value is None and shot_row is not None:
            shot_value = pbp_silver.to_int_or_none(shot_row.get("shotValue"))
        prefix = "off_3pt" if shot_value == 3 else "off_2pt"
        is_blocked = False
        if shot_row is not None:
            is_blocked = pbp_silver.to_int_or_none(shot_row.get("blockPersonId")) is not None
        return f"{prefix}_block" if is_blocked else f"{prefix}_miss"

    return "off_deadball"


def possession_end_type(row: dict[str, Any]) -> str | None:
    action_type = pbp_silver.normalized_action_type(row.get("actionType"))
    sub_type = pbp_silver.normalized_action_type(row.get("subType"))
    if action_type == "game" or (action_type == "period" and sub_type == "end"):
        return "period_end"
    reason = pbp_silver.null_if_empty(row.get("possessionBoundaryReason"))
    if pbp_silver.to_bool_or_none(row.get("isMadeShot")):
        return "made_shot"
    if pbp_silver.to_bool_or_none(row.get("isTurnover")):
        return "turnover"
    if pbp_silver.to_bool_or_none(row.get("isRebound")):
        if pbp_silver.to_bool_or_none(row.get("isDreb")):
            return "def_rebound"
        if pbp_silver.to_bool_or_none(row.get("isOreb")):
            return "rebound"
        return "rebound"
    if pbp_silver.to_bool_or_none(row.get("isFreeThrow")):
        return "free_throw"
    if pbp_silver.to_bool_or_none(row.get("isJumpBall")):
        return "jump_ball_change"
    if reason is not None:
        return str(reason)
    return "offense_change"


def normalize_pbpstats_start_type(value: Any) -> str | None:
    if value is None:
        return None
    mappings = {
        "OffDeadball": "off_deadball",
        "OffTimeout": "off_timeout",
        "OffFTMake": "off_ft_make",
        "OffFTMiss": "off_ft_miss",
        "OffLiveBallTurnover": "off_live_ball_turnover",
        "OffArc3Make": "off_3pt_make",
        "OffCorner3Make": "off_3pt_make",
        "OffArc3Miss": "off_3pt_miss",
        "OffCorner3Miss": "off_3pt_miss",
        "OffArc3Block": "off_3pt_block",
        "OffCorner3Block": "off_3pt_block",
        "OffAtRimMake": "off_2pt_make",
        "OffShortMidRangeMake": "off_2pt_make",
        "OffLongMidRangeMake": "off_2pt_make",
        "OffUnknownDistance2ptMake": "off_2pt_make",
        "OffAtRimMiss": "off_2pt_miss",
        "OffShortMidRangeMiss": "off_2pt_miss",
        "OffLongMidRangeMiss": "off_2pt_miss",
        "OffUnknownDistance2ptMiss": "off_2pt_miss",
        "OffAtRimBlock": "off_2pt_block",
        "OffShortMidRangeBlock": "off_2pt_block",
        "OffLongMidRangeBlock": "off_2pt_block",
        "OffUnknownDistance2ptBlock": "off_2pt_block",
    }
    text = str(value)
    return mappings.get(text, text)


def pbpstats_possession_end_type(possession: Possession) -> str | None:
    for candidate in reversed(possession.events):
        if getattr(candidate, "action_type", None) == "period" and getattr(candidate, "sub_type", None) == "end":
            return "period_end"
    event = possession_ending_event(possession.events)
    if isinstance(event, FieldGoal) and bool(getattr(event, "is_made", False)):
        return "made_shot"
    if isinstance(event, Turnover):
        return "turnover"
    if isinstance(event, Rebound):
        return "rebound" if bool(getattr(event, "oreb", False)) else "def_rebound"
    if isinstance(event, FreeThrow):
        return "free_throw"
    if isinstance(event, JumpBall):
        return "jump_ball_change"
    if (
        getattr(event, "action_type", None) == "period"
        and getattr(event, "sub_type", None) == "end"
    ) or getattr(event, "action_type", None) == "game":
        return "period_end"
    if isinstance(event, Timeout):
        return "offense_change"
    return "offense_change"


def pbpstats_points_scored_on_possession(possession: Possession) -> int | None:
    if getattr(possession, "previous_possession", None) is None:
        start_score = possession.events[0].score
    else:
        start_score = possession.previous_possession.events[-1].score
    end_score = possession.events[-1].score
    offense_team_id = possession.offense_team_id
    return int(end_score.get(offense_team_id, 0)) - int(start_score.get(offense_team_id, 0))


def known_team_ids_from_rows(
    playbyplay_rows: list[dict[str, Any]],
    on_court_rows: list[dict[str, Any]] | None = None,
) -> list[int]:
    team_ids: set[int] = set()
    for row in on_court_rows or []:
        home_team_id = pbp_silver.to_int_or_none(row.get("home_teamId"))
        away_team_id = pbp_silver.to_int_or_none(row.get("away_teamId"))
        if home_team_id is not None:
            team_ids.add(home_team_id)
        if away_team_id is not None:
            team_ids.add(away_team_id)
    if len(team_ids) == 2:
        return sorted(team_ids)

    for row in playbyplay_rows:
        for field in ("resolvedOffenseTeamId", "resolvedDefenseTeamId", "teamId"):
            team_id = pbp_silver.to_int_or_none(row.get(field))
            if team_id is not None:
                team_ids.add(team_id)
        if len(team_ids) == 2:
            break
    return sorted(team_ids)


def build_possession_rows_from_payload(
    payload: dict[str, Any],
    playbyplay_rows: list[dict[str, Any]],
    *,
    fallback_game_id: str | None = None,
    on_court_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    game_id, possessions = load_live_possession_items(payload, fallback_game_id=fallback_game_id)
    if not possessions:
        return []

    playbyplay_lookup = build_playbyplay_lookup(playbyplay_rows)
    known_team_ids = known_team_ids_from_rows(playbyplay_rows, on_court_rows=on_court_rows)
    finalized_rows: list[dict[str, Any]] = []

    for global_index, possession in enumerate(possessions, start=1):
        first_row, ending_row, previous_ending_row = possession_event_row_lookup(possession, playbyplay_lookup)
        first_event = possession.events[0]
        ending_event = possession_ending_event(possession.events)

        offense_team_id = pbp_silver.to_int_or_none(getattr(possession, "offense_team_id", None))
        defense_team_id = other_team_id(offense_team_id, known_team_ids)

        start_clock = getattr(possession, "start_time", None)
        end_clock = getattr(possession, "end_time", None)
        start_seconds = pbp_silver.parse_clock_to_seconds_remaining(start_clock)
        end_seconds = pbp_silver.parse_clock_to_seconds_remaining(end_clock)
        seconds_elapsed = None
        if start_seconds is not None and end_seconds is not None:
            seconds_elapsed = max(start_seconds - end_seconds, 0.0)

        offense_home_away = None
        defense_home_away = None
        for candidate_row in (first_row, ending_row):
            if candidate_row is None:
                continue
            if offense_home_away is None:
                offense_home_away = pbp_silver.null_if_empty(candidate_row.get("offenseHomeAway"))
            if defense_home_away is None:
                defense_home_away = pbp_silver.null_if_empty(candidate_row.get("defenseHomeAway"))
        if offense_home_away is None and on_court_rows:
            for row in on_court_rows:
                if pbp_silver.to_int_or_none(row.get("home_teamId")) == offense_team_id:
                    offense_home_away = "h"
                    defense_home_away = "v"
                    break
                if pbp_silver.to_int_or_none(row.get("away_teamId")) == offense_team_id:
                    offense_home_away = "v"
                    defense_home_away = "h"
                    break

        start_time_actual_utc = (
            parse_time_actual_utc(previous_ending_row.get("timeActual"))
            if previous_ending_row is not None
            else parse_time_actual_utc(first_row.get("timeActual") if first_row is not None else None)
        )
        end_time_actual_utc = parse_time_actual_utc(ending_row.get("timeActual") if ending_row is not None else None)

        possession_row: dict[str, Any] = {
            "gameId": str(game_id).zfill(10),
            "possessionNumber": global_index,
            "possessionNumberInPeriod": pbp_silver.to_int_or_none(getattr(possession, "number", None)),
            "period": pbp_silver.to_int_or_none(getattr(possession, "period", None)),
            "startActionNumber": pbp_silver.to_int_or_none(getattr(first_event, "event_num", None)),
            "endActionNumber": pbp_silver.to_int_or_none(getattr(ending_event, "event_num", None)),
            "startOrderNumber": pbp_silver.to_int_or_none(getattr(first_event, "order", None)),
            "endOrderNumber": pbp_silver.to_int_or_none(getattr(ending_event, "order", None)),
            "startClock": start_clock,
            "endClock": end_clock,
            "startTimeActualUtc": start_time_actual_utc,
            "endTimeActualUtc": end_time_actual_utc,
            "secondsElapsed": seconds_elapsed,
            "offenseTeamId": offense_team_id,
            "defenseTeamId": defense_team_id,
            "offenseHomeAway": None if offense_home_away is None else str(offense_home_away),
            "defenseHomeAway": None if defense_home_away is None else str(defense_home_away),
            "startScoreMargin": pbp_silver.to_int_or_none(getattr(possession, "start_score_margin", None)),
            "endScoreMargin": score_margin_from_score_dict(offense_team_id, possession.events[-1].score),
            "pointsScoredOnPossession": pbpstats_points_scored_on_possession(possession),
            "possessionStartType": normalize_pbpstats_start_type(getattr(possession, "possession_start_type", None)),
            "possessionEndType": pbpstats_possession_end_type(possession),
            "possessionBoundaryReason": (
                pbp_silver.null_if_empty(ending_row.get("possessionBoundaryReason"))
                if ending_row is not None
                else None
            ),
            "possessionHasTimeout": bool(getattr(possession, "possession_has_timeout", False)),
            "previousPossessionHasTimeout": bool(getattr(possession, "previous_possession_has_timeout", False)),
            "isSecondChancePossession": any(bool(event.is_second_chance_event()) for event in possession.events),
            "isPenaltyPossession": any(
                bool(event.is_penalty_event())
                for event in possession.events
                if getattr(event, "action_type", None) != "game"
            ),
            "countsAsPossession": bool(getattr(ending_event, "count_as_possession", False)),
            "previousPossessionNumber": (
                None
                if getattr(possession, "previous_possession", None) is None
                else global_index - 1
            ),
            "nextPossessionNumber": None,
            "previousPossessionEndingActionNumber": (
                None
                if getattr(possession, "previous_possession", None) is None
                else pbp_silver.to_int_or_none(
                    getattr(possession_ending_event(possession.previous_possession.events), "event_num", None)
                )
            ),
            "homeLineupId": None,
            "awayLineupId": None,
            "lineupValidFlag": None,
            "lineupIssue": None,
            "fieldGoalAttempts": sum(1 for event in possession.events if isinstance(event, FieldGoal)),
            "freeThrowAttempts": sum(1 for event in possession.events if isinstance(event, FreeThrow)),
            "turnovers": sum(1 for event in possession.events if isinstance(event, Turnover)),
            "offensiveRebounds": sum(
                1
                for event in possession.events
                if isinstance(event, Rebound)
                and bool(getattr(event, "oreb", False))
                and bool(getattr(event, "is_real_rebound", False))
            ),
            "madeFieldGoals": sum(
                1 for event in possession.events if isinstance(event, FieldGoal) and bool(getattr(event, "is_made", False))
            ),
        }
        if finalized_rows:
            finalized_rows[-1]["nextPossessionNumber"] = possession_row["possessionNumber"]
        finalized_rows.append(possession_row)

    if on_court_rows is not None:
        finalized_rows = stamp_lineup_context(finalized_rows, on_court_rows)
    return finalized_rows


def build_possession_rows_from_events(
    rows: list[dict[str, Any]],
    on_court_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    sorted_rows = sort_event_rows(rows)
    game_id = first_non_null(sorted_rows, "gameId")
    possessions: list[dict[str, Any]] = []
    current_events: list[dict[str, Any]] = []
    global_number = 0
    number_in_period = 0
    current_period: int | None = None
    previous_possession: dict[str, Any] | None = None

    for row in sorted_rows:
        row_period = pbp_silver.to_int_or_none(row.get("period"))
        if row_period != current_period:
            current_period = row_period
            number_in_period = 0

        current_events.append(row)
        if not pbp_silver.to_bool_or_none(row.get("isPossessionEndingEvent")):
            continue

        global_number += 1
        number_in_period += 1

        possession_events = list(current_events)
        current_events = []
        first_row = possession_events[0]
        ending_row = ending_event_row(possession_events)
        period_start_possession = any(pbp_silver.is_start_of_period_row(event) for event in possession_events)

        prior_for_context = (
            previous_possession
            if previous_possession is not None and not period_start_possession
            else None
        )
        previous_events = None if prior_for_context is None else prior_for_context["_events"]

        start_clock = (
            prior_for_context.get("endClock")
            if prior_for_context is not None
            else pbp_silver.null_if_empty(first_row.get("clock"))
        )
        end_clock = pbp_silver.null_if_empty(ending_row.get("clock"))

        possession_has_timeout = possession_timeout_flag(possession_events, end_clock)
        previous_possession_has_timeout = previous_possession_timeout_flag(previous_events, start_clock)

        offense_team_id = pbp_silver.to_int_or_none(first_non_null(possession_events, "resolvedOffenseTeamId"))
        defense_team_id = pbp_silver.to_int_or_none(first_non_null(possession_events, "resolvedDefenseTeamId"))
        offense_home_away = first_non_null(possession_events, "offenseHomeAway")
        defense_home_away = first_non_null(possession_events, "defenseHomeAway")

        if prior_for_context is not None:
            start_score_home = prior_for_context["_endScoreHome"]
            start_score_away = prior_for_context["_endScoreAway"]
            start_time_actual_utc = prior_for_context["endTimeActualUtc"]
        else:
            start_score_home = pbp_silver.to_int_or_none(first_row.get("scoreHome"))
            start_score_away = pbp_silver.to_int_or_none(first_row.get("scoreAway"))
            start_time_actual_utc = parse_time_actual_utc(first_row.get("timeActual"))

        end_score_home = pbp_silver.to_int_or_none(ending_row.get("scoreHome"))
        end_score_away = pbp_silver.to_int_or_none(ending_row.get("scoreAway"))
        end_time_actual_utc = parse_time_actual_utc(ending_row.get("timeActual"))

        start_score_margin = None
        if offense_home_away is not None and start_score_home is not None and start_score_away is not None:
            if str(offense_home_away) == "h":
                start_score_margin = start_score_home - start_score_away
            elif str(offense_home_away) == "v":
                start_score_margin = start_score_away - start_score_home

        end_score_margin = None
        if offense_home_away is not None and end_score_home is not None and end_score_away is not None:
            if str(offense_home_away) == "h":
                end_score_margin = end_score_home - end_score_away
            elif str(offense_home_away) == "v":
                end_score_margin = end_score_away - end_score_home
        start_points = score_points_for_location(start_score_home, start_score_away, offense_home_away)
        end_points = score_points_for_location(end_score_home, end_score_away, offense_home_away)
        points_scored_on_possession = None
        if start_points is not None and end_points is not None:
            points_scored_on_possession = end_points - start_points

        start_seconds = pbp_silver.parse_clock_to_seconds_remaining(start_clock)
        end_seconds = pbp_silver.parse_clock_to_seconds_remaining(end_clock)
        seconds_elapsed = None
        if start_seconds is not None and end_seconds is not None:
            seconds_elapsed = max(start_seconds - end_seconds, 0.0)

        possession_row: dict[str, Any] = {
            "gameId": game_id,
            "possessionNumber": global_number,
            "possessionNumberInPeriod": number_in_period,
            "period": row_period,
            "startActionNumber": pbp_silver.to_int_or_none(first_row.get("actionNumber")),
            "endActionNumber": pbp_silver.to_int_or_none(ending_row.get("actionNumber")),
            "startOrderNumber": pbp_silver.to_int_or_none(first_row.get("orderNumber")),
            "endOrderNumber": pbp_silver.to_int_or_none(ending_row.get("orderNumber")),
            "startClock": start_clock,
            "endClock": end_clock,
            "startTimeActualUtc": start_time_actual_utc,
            "endTimeActualUtc": end_time_actual_utc,
            "secondsElapsed": seconds_elapsed,
            "offenseTeamId": offense_team_id,
            "defenseTeamId": defense_team_id,
            "offenseHomeAway": None if offense_home_away is None else str(offense_home_away),
            "defenseHomeAway": None if defense_home_away is None else str(defense_home_away),
            "startScoreMargin": start_score_margin,
            "endScoreMargin": end_score_margin,
            "pointsScoredOnPossession": points_scored_on_possession,
            "possessionStartType": possession_start_type_from_previous(
                previous_events,
                possession_has_timeout,
                previous_possession_has_timeout,
            ),
            "possessionEndType": possession_end_type(ending_row),
            "possessionBoundaryReason": pbp_silver.null_if_empty(ending_row.get("possessionBoundaryReason")),
            "possessionHasTimeout": possession_has_timeout,
            "previousPossessionHasTimeout": previous_possession_has_timeout,
            "isSecondChancePossession": any(
                pbp_silver.to_bool_or_none(event.get("isSecondChanceEvent")) for event in possession_events
            ),
            "isPenaltyPossession": any(
                pbp_silver.to_bool_or_none(event.get("isPenaltyEvent")) for event in possession_events
            ),
            "countsAsPossession": bool(pbp_silver.to_bool_or_none(ending_row.get("countAsPossession"))),
            "previousPossessionNumber": None if prior_for_context is None else prior_for_context["possessionNumber"],
            "nextPossessionNumber": None,
            "previousPossessionEndingActionNumber": (
                None if prior_for_context is None else prior_for_context["endActionNumber"]
            ),
            "homeLineupId": None,
            "awayLineupId": None,
            "lineupValidFlag": None,
            "lineupIssue": None,
            "fieldGoalAttempts": sum(
                1
                for event in possession_events
                if pbp_silver.to_bool_or_none(event.get("isMadeShot"))
                or pbp_silver.to_bool_or_none(event.get("isMissedShot"))
            ),
            "freeThrowAttempts": sum(
                1 for event in possession_events if pbp_silver.to_bool_or_none(event.get("isFreeThrow"))
            ),
            "turnovers": sum(
                1 for event in possession_events if pbp_silver.to_bool_or_none(event.get("isTurnover"))
            ),
            "offensiveRebounds": sum(
                1
                for event_index, event in enumerate(possession_events)
                if pbp_silver.to_bool_or_none(event.get("isOreb"))
                and is_real_rebound_event(possession_events, event_index)
            ),
            "madeFieldGoals": sum(
                1 for event in possession_events if pbp_silver.to_bool_or_none(event.get("isMadeShot"))
            ),
            "_events": possession_events,
            "_endScoreHome": end_score_home,
            "_endScoreAway": end_score_away,
        }

        if previous_possession is not None:
            previous_possession["nextPossessionNumber"] = possession_row["possessionNumber"]

        possessions.append(possession_row)
        previous_possession = possession_row

    if current_events:
        global_number += 1
        number_in_period += 1
        first_row = current_events[0]
        last_row = current_events[-1]
        possession_row = {
            "gameId": game_id,
            "possessionNumber": global_number,
            "possessionNumberInPeriod": number_in_period,
            "period": pbp_silver.to_int_or_none(first_row.get("period")),
            "startActionNumber": pbp_silver.to_int_or_none(first_row.get("actionNumber")),
            "endActionNumber": pbp_silver.to_int_or_none(last_row.get("actionNumber")),
            "startOrderNumber": pbp_silver.to_int_or_none(first_row.get("orderNumber")),
            "endOrderNumber": pbp_silver.to_int_or_none(last_row.get("orderNumber")),
            "startClock": pbp_silver.null_if_empty(first_row.get("clock")),
            "endClock": pbp_silver.null_if_empty(last_row.get("clock")),
            "startTimeActualUtc": parse_time_actual_utc(first_row.get("timeActual")),
            "endTimeActualUtc": parse_time_actual_utc(last_row.get("timeActual")),
            "secondsElapsed": None,
            "offenseTeamId": pbp_silver.to_int_or_none(first_non_null(current_events, "resolvedOffenseTeamId")),
            "defenseTeamId": pbp_silver.to_int_or_none(first_non_null(current_events, "resolvedDefenseTeamId")),
            "offenseHomeAway": first_non_null(current_events, "offenseHomeAway"),
            "defenseHomeAway": first_non_null(current_events, "defenseHomeAway"),
            "startScoreMargin": pbp_silver.to_int_or_none(first_row.get("scoreMarginBefore")),
            "endScoreMargin": pbp_silver.to_int_or_none(last_row.get("scoreMarginAfter")),
            "pointsScoredOnPossession": None,
            "possessionStartType": "off_deadball",
            "possessionEndType": possession_end_type(last_row),
            "possessionBoundaryReason": pbp_silver.null_if_empty(last_row.get("possessionBoundaryReason")),
            "possessionHasTimeout": possession_timeout_flag(current_events, last_row.get("clock")),
            "previousPossessionHasTimeout": False,
            "isSecondChancePossession": any(
                pbp_silver.to_bool_or_none(event.get("isSecondChanceEvent")) for event in current_events
            ),
            "isPenaltyPossession": any(
                pbp_silver.to_bool_or_none(event.get("isPenaltyEvent")) for event in current_events
            ),
            "countsAsPossession": False,
            "previousPossessionNumber": None if previous_possession is None else previous_possession["possessionNumber"],
            "nextPossessionNumber": None,
            "previousPossessionEndingActionNumber": (
                None if previous_possession is None else previous_possession["endActionNumber"]
            ),
            "homeLineupId": None,
            "awayLineupId": None,
            "lineupValidFlag": None,
            "lineupIssue": None,
            "fieldGoalAttempts": sum(
                1
                for event in current_events
                if pbp_silver.to_bool_or_none(event.get("isMadeShot"))
                or pbp_silver.to_bool_or_none(event.get("isMissedShot"))
            ),
            "freeThrowAttempts": sum(
                1 for event in current_events if pbp_silver.to_bool_or_none(event.get("isFreeThrow"))
            ),
            "turnovers": sum(
                1 for event in current_events if pbp_silver.to_bool_or_none(event.get("isTurnover"))
            ),
            "offensiveRebounds": sum(
                1
                for event_index, event in enumerate(current_events)
                if pbp_silver.to_bool_or_none(event.get("isOreb"))
                and is_real_rebound_event(current_events, event_index)
            ),
            "madeFieldGoals": sum(
                1 for event in current_events if pbp_silver.to_bool_or_none(event.get("isMadeShot"))
            ),
            "_events": current_events,
            "_endScoreHome": pbp_silver.to_int_or_none(last_row.get("scoreHome")),
            "_endScoreAway": pbp_silver.to_int_or_none(last_row.get("scoreAway")),
        }
        if previous_possession is not None:
            previous_possession["nextPossessionNumber"] = possession_row["possessionNumber"]
        possessions.append(possession_row)

    finalized_rows: list[dict[str, Any]] = []
    for possession in possessions:
        finalized_rows.append({column: possession.get(column) for column in EXACT_TARGET_COLUMNS})
    if on_court_rows is not None:
        finalized_rows = stamp_lineup_context(finalized_rows, on_court_rows)
    return finalized_rows
