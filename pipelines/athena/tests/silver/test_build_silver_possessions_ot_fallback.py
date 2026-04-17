from __future__ import annotations

import sys
from pathlib import Path


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_possessions as base
import build_silver_possessions_ot_fallback as fallback
from pbpstats_projection_common import InvalidNumberOfStartersException


def make_action(**overrides):
    action = {
        "actionNumber": 1,
        "orderNumber": 100,
        "clock": "PT05M00.00S",
        "period": 5,
        "actionType": "period",
        "subType": "start",
        "personId": 0,
        "teamId": None,
        "description": "Period Start",
    }
    action.update(overrides)
    return action


def make_payload(*actions, game_id: str = "0022400999"):
    return {"game": {"gameId": game_id, "actions": list(actions)}}


def make_stint(*, period, stint_id, start_order, end_order, home_ids, away_ids, valid=1, issue=None):
    return {
        "gameId": "0022400999",
        "period": period,
        "stint_id": stint_id,
        "start_orderNumber": start_order,
        "end_orderNumber": end_order,
        "start_clock": "PT05M00.00S" if period >= 5 else "PT12M00.00S",
        "home_teamId": 1610612737,
        "away_teamId": 1610612738,
        "home_personIds": home_ids,
        "away_personIds": away_ids,
        "lineup_valid_flag": valid,
        "lineup_issue": issue,
    }


def make_event(**overrides):
    event = {
        "gameId": "0022400999",
        "period": 5,
        "actionNumber": 1,
        "orderNumber": 100,
        "clock": "PT05M00.00S",
        "secondsRemainingInPeriod": 300.0,
        "timeActual": None,
        "scoreHome": 100,
        "scoreAway": 100,
        "scoreMarginBefore": 0,
        "scoreMarginAfter": 0,
        "resolvedOffenseTeamId": 1610612737,
        "resolvedDefenseTeamId": 1610612738,
        "offenseHomeAway": "h",
        "defenseHomeAway": "v",
        "shotResult": None,
        "shotActionNumber": None,
        "shotValue": None,
        "blockPersonId": None,
        "personId": None,
        "teamId": None,
        "stealPersonId": None,
        "qualifiers": None,
        "subType": None,
        "descriptor": None,
        "actionType": "period",
        "isMadeShot": False,
        "isMissedShot": False,
        "isFreeThrow": False,
        "isRebound": False,
        "isTurnover": False,
        "isSubstitution": False,
        "isTimeout": False,
        "isJumpBall": False,
        "isOreb": False,
        "isDreb": False,
        "isPlaceholderRebound": False,
        "isTechnicalFt": False,
        "isFlagrantFt": False,
        "isSecondChanceEvent": False,
        "isPenaltyEvent": False,
        "isPossessionEndingEvent": False,
        "countAsPossession": False,
        "possessionBoundaryReason": None,
    }
    event.update(overrides)
    return event


def test_recoverable_reference_failure_only_allows_ot_starter_exceptions():
    assert fallback.is_recoverable_reference_failure(
        InvalidNumberOfStartersException("GameId: 1, Period: 5, TeamId: 1, Players: []")
    )
    assert not fallback.is_recoverable_reference_failure(
        InvalidNumberOfStartersException("GameId: 1, Period: 3, TeamId: 1, Players: []")
    )
    assert not fallback.is_recoverable_reference_failure(AttributeError("bad event"))


def test_build_recovered_ot_stints_reuses_prior_period_when_no_opening_subs():
    prior = make_stint(
        period=4,
        stint_id=7,
        start_order=500,
        end_order=600,
        home_ids=[1, 2, 3, 4, 5],
        away_ids=[6, 7, 8, 9, 10],
    )
    payload = make_payload(
        make_action(actionNumber=700, orderNumber=7000, description="Period Start"),
        make_action(
            actionNumber=701,
            orderNumber=7010,
            clock="PT04M58.00S",
            actionType="jumpball",
            subType="recovered",
            personId=1,
            teamId=1610612737,
        ),
    )
    recovered = fallback.build_recovered_ot_stints(payload, failed_period=5, prior_stint=prior)
    assert recovered is not None
    stints, opening_applied = recovered
    assert opening_applied is False
    assert len(stints) == 1
    assert stints[0]["home_personIds"] == [1, 2, 3, 4, 5]
    assert stints[0]["away_personIds"] == [6, 7, 8, 9, 10]


def test_build_recovered_ot_stints_applies_clean_opening_cluster():
    prior = make_stint(
        period=4,
        stint_id=7,
        start_order=500,
        end_order=600,
        home_ids=[1, 2, 3, 4, 5],
        away_ids=[6, 7, 8, 9, 10],
    )
    payload = make_payload(
        make_action(actionNumber=660, orderNumber=6500, actionType="substitution", subType="out", personId=1, teamId=1610612737),
        make_action(actionNumber=661, orderNumber=6510, actionType="substitution", subType="in", personId=11, teamId=1610612737),
        make_action(actionNumber=662, orderNumber=6520, description="Period Start"),
        make_action(
            actionNumber=663,
            orderNumber=6530,
            clock="PT04M58.00S",
            actionType="jumpball",
            subType="recovered",
            personId=11,
            teamId=1610612737,
        ),
    )
    recovered = fallback.build_recovered_ot_stints(payload, failed_period=5, prior_stint=prior)
    assert recovered is not None
    stints, opening_applied = recovered
    assert opening_applied is True
    assert stints[0]["home_personIds"] == [2, 3, 4, 5, 11]


def test_build_recovered_ot_stints_allows_one_sided_opening_cluster():
    prior = make_stint(
        period=4,
        stint_id=7,
        start_order=500,
        end_order=600,
        home_ids=[1, 2, 3, 4, 5],
        away_ids=[6, 7, 8, 9, 10],
    )
    payload = make_payload(
        make_action(actionNumber=660, orderNumber=6500, actionType="substitution", subType="out", personId=6, teamId=1610612738),
        make_action(actionNumber=661, orderNumber=6510, actionType="substitution", subType="in", personId=12, teamId=1610612738),
        make_action(actionNumber=662, orderNumber=6520, description="Period Start"),
    )
    recovered = fallback.build_recovered_ot_stints(payload, failed_period=5, prior_stint=prior)
    assert recovered is not None
    stints, _ = recovered
    assert stints[0]["home_personIds"] == [1, 2, 3, 4, 5]
    assert stints[0]["away_personIds"] == [7, 8, 9, 10, 12]


def test_build_recovered_ot_stints_refuses_invalid_cluster():
    prior = make_stint(
        period=4,
        stint_id=7,
        start_order=500,
        end_order=600,
        home_ids=[1, 2, 3, 4, 5],
        away_ids=[6, 7, 8, 9, 10],
    )
    payload = make_payload(
        make_action(actionNumber=660, orderNumber=6500, actionType="substitution", subType="out", personId=999, teamId=1610612737),
        make_action(actionNumber=661, orderNumber=6510, description="Period Start"),
    )
    assert fallback.build_recovered_ot_stints(payload, failed_period=5, prior_stint=prior) is None


def test_build_effective_on_court_rows_skips_when_no_valid_prior_period():
    payload = make_payload(make_action(actionNumber=700, orderNumber=7000))
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=200, home_ids=[1, 2, 3, 4], away_ids=[6, 7, 8, 9, 10], valid=0, issue="home_lineup_size=4")
    ]
    assert fallback.build_effective_on_court_rows(payload, on_court_rows, failed_period=5) is None


def test_build_stale_sub_out_repaired_on_court_rows_sanitizes_failed_ot_period():
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=600, home_ids=[1, 2, 3, 4, 5], away_ids=[6, 7, 8, 9, 10], valid=0, issue="sub_out_not_in_lineup(side=away,period=4,order=500,personId=6)"),
        make_stint(period=5, stint_id=2, start_order=700, end_order=800, home_ids=[11, 12, 13, 14, 15], away_ids=[16, 17, 18, 19, 20], valid=0, issue="sub_out_not_in_lineup(side=away,period=4,order=500,personId=6)"),
        make_stint(period=5, stint_id=3, start_order=800, end_order=900, home_ids=[11, 12, 13, 14, 15], away_ids=[16, 17, 18, 19, 20], valid=0, issue="sub_out_not_in_lineup(side=away,period=4,order=500,personId=6) | sub_out_not_in_lineup(side=away,period=4,order=550,personId=7)"),
    ]
    rebuilt = fallback.build_stale_sub_out_repaired_on_court_rows(on_court_rows, failed_period=5)
    assert rebuilt is not None
    effective_rows, opening_applied = rebuilt
    assert opening_applied is False
    period_5_rows = [row for row in effective_rows if row["period"] == 5]
    assert len(period_5_rows) == 2
    assert all(row["lineup_valid_flag"] == 1 for row in period_5_rows)
    assert all(row["lineup_issue"] is None for row in period_5_rows)
    period_4_rows = [row for row in effective_rows if row["period"] == 4]
    assert period_4_rows[0]["lineup_valid_flag"] == 0


def test_build_stale_sub_out_repaired_on_court_rows_refuses_lineup_size_issues():
    on_court_rows = [
        make_stint(period=5, stint_id=1, start_order=700, end_order=800, home_ids=[11, 12, 13, 14], away_ids=[16, 17, 18, 19, 20], valid=0, issue="home_lineup_size=4"),
    ]
    assert fallback.build_stale_sub_out_repaired_on_court_rows(on_court_rows, failed_period=5) is None


def test_build_stale_sub_out_repaired_on_court_rows_refuses_non_stale_issue_types():
    on_court_rows = [
        make_stint(period=5, stint_id=1, start_order=700, end_order=800, home_ids=[11, 12, 13, 14, 15], away_ids=[16, 17, 18, 19, 20], valid=0, issue="sub_in_already_in_lineup(side=home,period=5,order=700,personId=11)"),
    ]
    assert fallback.build_stale_sub_out_repaired_on_court_rows(on_court_rows, failed_period=5) is None


def test_build_end_q4_drift_reconciled_on_court_rows_recovers_partial_ot_lineups():
    payload = make_payload(
        make_action(period=5, actionNumber=660, orderNumber=6500, actionType="substitution", subType="out", personId=1, teamId=1610612737),
        make_action(period=5, actionNumber=661, orderNumber=6510, actionType="substitution", subType="in", personId=11, teamId=1610612737),
        make_action(period=5, actionNumber=662, orderNumber=6520, actionType="substitution", subType="out", personId=6, teamId=1610612738),
        make_action(period=5, actionNumber=663, orderNumber=6530, actionType="substitution", subType="in", personId=16, teamId=1610612738),
        make_action(period=5, actionNumber=664, orderNumber=6540, description="Period Start"),
    )
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=600, home_ids=[1, 2, 3, 4, 5], away_ids=[6, 7, 8, 9, 10]),
        make_stint(period=4, stint_id=2, start_order=600, end_order=650, home_ids=[1, 3, 4, 5], away_ids=[6, 8, 9, 10], valid=0, issue="home_lineup_size=4 | away_lineup_size=4"),
        make_stint(period=5, stint_id=3, start_order=650, end_order=700, home_ids=[1, 3, 4, 5], away_ids=[6, 8, 9, 10], valid=0, issue="home_lineup_size=4 | away_lineup_size=4"),
    ]
    rebuilt = fallback.build_end_q4_drift_reconciled_on_court_rows(payload, on_court_rows, failed_period=5)
    assert rebuilt is not None
    effective_rows, opening_applied = rebuilt
    assert opening_applied is True
    period_5_rows = [row for row in effective_rows if row["period"] == 5]
    assert len(period_5_rows) == 1
    assert period_5_rows[0]["home_personIds"] == [1, 3, 4, 5, 11]
    assert period_5_rows[0]["away_personIds"] == [6, 8, 9, 10, 16]
    assert period_5_rows[0]["lineup_valid_flag"] == 1
    assert period_5_rows[0]["lineup_issue"] is None


def test_build_end_q4_drift_reconciled_on_court_rows_refuses_when_too_many_missing_players():
    payload = make_payload(
        make_action(period=5, actionNumber=660, orderNumber=6500, actionType="substitution", subType="out", personId=1, teamId=1610612737),
        make_action(period=5, actionNumber=661, orderNumber=6510, actionType="substitution", subType="in", personId=11, teamId=1610612737),
        make_action(period=5, actionNumber=662, orderNumber=6520, description="Period Start"),
    )
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=600, home_ids=[1, 2, 3, 4, 5], away_ids=[6, 7, 8, 9, 10]),
        make_stint(period=4, stint_id=2, start_order=600, end_order=650, home_ids=[1, 4, 5], away_ids=[6, 7, 8, 9, 10], valid=0, issue="home_lineup_size=3"),
        make_stint(period=5, stint_id=3, start_order=650, end_order=700, home_ids=[1, 4, 5], away_ids=[6, 7, 8, 9, 10], valid=0, issue="home_lineup_size=3"),
    ]
    assert fallback.build_end_q4_drift_reconciled_on_court_rows(payload, on_court_rows, failed_period=5) is None


def test_build_fallback_rows_for_game_marks_provenance_fields():
    payload = make_payload(
        make_action(actionNumber=700, orderNumber=7000),
        game_id="0022400999",
    )
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=600, home_ids=[1, 2, 3, 4, 5], away_ids=[6, 7, 8, 9, 10]),
    ]
    playbyplay_rows = [
        make_event(actionNumber=700, orderNumber=7000, actionType="period", subType="start"),
        make_event(
            actionNumber=701,
            orderNumber=7010,
            clock="PT04M50.00S",
            actionType="turnover",
            isTurnover=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="turnover",
        ),
    ]
    result = fallback.build_fallback_rows_for_game(
        payload,
        playbyplay_rows,
        on_court_rows,
        reference_failure=InvalidNumberOfStartersException("GameId: 0022400999, Period: 5, TeamId: 1, Players: []"),
    )
    assert result is not None
    rows, failed_period, opening_applied, source_method = result
    assert failed_period == 5
    assert opening_applied is False
    assert source_method == "fallback_ot_carry_forward"
    assert rows[0]["possessionSourceMethod"] == "fallback_ot_carry_forward"
    assert rows[0]["referenceFailureType"] == "InvalidNumberOfStartersException"
    assert rows[0]["referenceFailurePeriod"] == 5
    assert rows[0]["fallbackApplied"] is True
    assert rows[0]["fallbackOpeningSubClusterApplied"] is False


def test_build_fallback_rows_for_game_prefers_stale_sub_out_repair_when_ot_lineups_are_complete():
    payload = make_payload(
        make_action(actionNumber=700, orderNumber=7000),
        game_id="0022400999",
    )
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=600, home_ids=[1, 2, 3, 4, 5], away_ids=[6, 7, 8, 9, 10], valid=0, issue="sub_out_not_in_lineup(side=away,period=4,order=500,personId=6)"),
        make_stint(period=5, stint_id=2, start_order=700, end_order=800, home_ids=[11, 12, 13, 14, 15], away_ids=[16, 17, 18, 19, 20], valid=0, issue="sub_out_not_in_lineup(side=away,period=4,order=500,personId=6)"),
        make_stint(period=5, stint_id=3, start_order=800, end_order=900, home_ids=[11, 12, 13, 14, 15], away_ids=[16, 17, 18, 19, 20], valid=0, issue="sub_out_not_in_lineup(side=away,period=4,order=500,personId=6)"),
    ]
    playbyplay_rows = [
        make_event(actionNumber=700, orderNumber=7000, actionType="period", subType="start"),
        make_event(
            actionNumber=701,
            orderNumber=7010,
            clock="PT04M50.00S",
            actionType="turnover",
            isTurnover=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="turnover",
        ),
    ]
    result = fallback.build_fallback_rows_for_game(
        payload,
        playbyplay_rows,
        on_court_rows,
        reference_failure=InvalidNumberOfStartersException("GameId: 0022400999, Period: 5, TeamId: 1, Players: []"),
    )
    assert result is not None
    rows, failed_period, opening_applied, source_method = result
    assert failed_period == 5
    assert opening_applied is False
    assert source_method == "fallback_ot_stale_sub_out_repair"
    assert rows[0]["possessionSourceMethod"] == "fallback_ot_stale_sub_out_repair"
    assert rows[0]["fallbackOpeningSubClusterApplied"] is False


def test_build_fallback_rows_for_game_uses_end_q4_drift_reconcile_before_carry_forward():
    payload = make_payload(
        make_action(period=5, actionNumber=660, orderNumber=6500, actionType="substitution", subType="out", personId=1, teamId=1610612737),
        make_action(period=5, actionNumber=661, orderNumber=6510, actionType="substitution", subType="in", personId=11, teamId=1610612737),
        make_action(period=5, actionNumber=662, orderNumber=6520, actionType="substitution", subType="out", personId=6, teamId=1610612738),
        make_action(period=5, actionNumber=663, orderNumber=6530, actionType="substitution", subType="in", personId=16, teamId=1610612738),
        make_action(period=5, actionNumber=664, orderNumber=6540, description="Period Start"),
        game_id="0022400999",
    )
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=600, home_ids=[1, 2, 3, 4, 5], away_ids=[6, 7, 8, 9, 10]),
        make_stint(period=4, stint_id=2, start_order=600, end_order=650, home_ids=[1, 3, 4, 5], away_ids=[6, 8, 9, 10], valid=0, issue="home_lineup_size=4 | away_lineup_size=4"),
        make_stint(period=5, stint_id=3, start_order=650, end_order=700, home_ids=[1, 3, 4, 5], away_ids=[6, 8, 9, 10], valid=0, issue="home_lineup_size=4 | away_lineup_size=4"),
    ]
    playbyplay_rows = [
        make_event(actionNumber=660, orderNumber=6500, actionType="substitution", subType="out", teamId=1610612737, personId=1, isSubstitution=True),
        make_event(actionNumber=661, orderNumber=6510, actionType="substitution", subType="in", teamId=1610612737, personId=11, isSubstitution=True),
        make_event(actionNumber=662, orderNumber=6520, actionType="substitution", subType="out", teamId=1610612738, personId=6, isSubstitution=True),
        make_event(actionNumber=663, orderNumber=6530, actionType="substitution", subType="in", teamId=1610612738, personId=16, isSubstitution=True),
        make_event(actionNumber=664, orderNumber=6540, actionType="period", subType="start"),
        make_event(
            actionNumber=665,
            orderNumber=6550,
            clock="PT04M50.00S",
            actionType="turnover",
            isTurnover=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="turnover",
        ),
    ]
    result = fallback.build_fallback_rows_for_game(
        payload,
        playbyplay_rows,
        on_court_rows,
        reference_failure=InvalidNumberOfStartersException("GameId: 0022400999, Period: 5, TeamId: 1, Players: []"),
    )
    assert result is not None
    rows, failed_period, opening_applied, source_method = result
    assert failed_period == 5
    assert opening_applied is True
    assert source_method == "fallback_ot_end_q4_drift_reconcile"
    assert rows[0]["possessionSourceMethod"] == "fallback_ot_end_q4_drift_reconcile"
    assert rows[0]["fallbackOpeningSubClusterApplied"] is True


def test_build_fallback_rows_for_game_refuses_regulation_failures():
    payload = make_payload(game_id="0022400999")
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=600, home_ids=[1, 2, 3, 4, 5], away_ids=[6, 7, 8, 9, 10]),
    ]
    playbyplay_rows = [make_event()]
    assert (
        fallback.build_fallback_rows_for_game(
            payload,
            playbyplay_rows,
            on_court_rows,
            reference_failure=InvalidNumberOfStartersException("GameId: 0022400999, Period: 3, TeamId: 1, Players: []"),
        )
        is None
    )


def test_build_fallback_rows_for_game_refuses_attribute_error_failures():
    payload = make_payload(game_id="0022400999")
    on_court_rows = [
        make_stint(period=4, stint_id=1, start_order=100, end_order=600, home_ids=[1, 2, 3, 4, 5], away_ids=[6, 7, 8, 9, 10]),
    ]
    playbyplay_rows = [make_event()]
    assert (
        fallback.build_fallback_rows_for_game(
            payload,
            playbyplay_rows,
            on_court_rows,
            reference_failure=AttributeError("bad event"),
        )
        is None
    )
