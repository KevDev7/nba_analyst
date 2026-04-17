from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


SILVER_TRANSFORM_DIR = (
    Path(__file__).resolve().parents[2] / "transform" / "silver"
)
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_possessions as possessions_silver


def make_event(**overrides):
    event = {
        "gameId": "0022400999",
        "period": 1,
        "actionNumber": 1,
        "orderNumber": 100,
        "clock": "PT12M00.00S",
        "secondsRemainingInPeriod": 720.0,
        "timeActual": None,
        "scoreHome": 0,
        "scoreAway": 0,
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


def test_target_schema_includes_silver_metadata_columns():
    schema_names = set(possessions_silver.TARGET_SCHEMA.names)
    for column in [
        "_meta_pipeline_run_id",
        "_meta_ingested_at_utc",
        "_meta_source_system",
        "_meta_source_key",
        "_meta_source_last_modified_utc",
        "_meta_schema_version",
    ]:
        assert column in schema_names


def test_build_possession_rows_from_events_creates_core_rows_and_links():
    rows = [
        make_event(actionNumber=1, orderNumber=100, actionType="period", subType="start"),
        make_event(
            actionNumber=2,
            orderNumber=110,
            actionType="2pt",
            clock="PT11M40.00S",
            scoreHome=2,
            scoreAway=0,
            scoreMarginBefore=0,
            scoreMarginAfter=2,
            shotValue=2,
            isMadeShot=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="made_shot",
        ),
        make_event(
            actionNumber=3,
            orderNumber=120,
            actionType="timeout",
            clock="PT11M20.00S",
            scoreHome=2,
            scoreAway=0,
            scoreMarginBefore=-2,
            scoreMarginAfter=-2,
            resolvedOffenseTeamId=1610612738,
            resolvedDefenseTeamId=1610612737,
            offenseHomeAway="v",
            defenseHomeAway="h",
            isTimeout=True,
        ),
        make_event(
            actionNumber=4,
            orderNumber=130,
            actionType="turnover",
            clock="PT11M10.00S",
            scoreHome=2,
            scoreAway=0,
            scoreMarginBefore=-2,
            scoreMarginAfter=-2,
            resolvedOffenseTeamId=1610612738,
            resolvedDefenseTeamId=1610612737,
            offenseHomeAway="v",
            defenseHomeAway="h",
            teamId=1610612738,
            isTurnover=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="turnover",
        ),
    ]

    possession_rows = possessions_silver.build_possession_rows_from_events(rows)

    assert len(possession_rows) == 2

    first = possession_rows[0]
    assert first["possessionNumber"] == 1
    assert first["possessionNumberInPeriod"] == 1
    assert first["startClock"] == "PT12M00.00S"
    assert first["endClock"] == "PT11M40.00S"
    assert first["secondsElapsed"] == 20.0
    assert first["pointsScoredOnPossession"] == 2
    assert first["startScoreMargin"] == 0
    assert first["endScoreMargin"] == 2
    assert first["possessionStartType"] == "off_deadball"
    assert first["possessionEndType"] == "made_shot"
    assert first["countsAsPossession"] is True
    assert first["nextPossessionNumber"] == 2

    second = possession_rows[1]
    assert second["possessionNumber"] == 2
    assert second["previousPossessionNumber"] == 1
    assert second["previousPossessionEndingActionNumber"] == 2
    assert second["startClock"] == "PT11M40.00S"
    assert second["endClock"] == "PT11M10.00S"
    assert second["secondsElapsed"] == 30.0
    assert second["startScoreMargin"] == -2
    assert second["pointsScoredOnPossession"] == 0
    assert second["possessionStartType"] == "off_timeout"
    assert second["possessionHasTimeout"] is True
    assert second["possessionEndType"] == "turnover"


def test_build_possession_rows_from_events_uses_rebound_and_period_context():
    rows = [
        make_event(
            gameId="0022401000",
            actionNumber=10,
            orderNumber=100,
            period=1,
            actionType="3pt",
            clock="PT00M20.00S",
            scoreHome=80,
            scoreAway=80,
            scoreMarginBefore=0,
            scoreMarginAfter=0,
            shotValue=3,
            isMissedShot=True,
        ),
        make_event(
            gameId="0022401000",
            actionNumber=11,
            orderNumber=110,
            period=1,
            actionType="rebound",
            clock="PT00M18.00S",
            scoreHome=80,
            scoreAway=80,
            scoreMarginBefore=0,
            scoreMarginAfter=0,
            resolvedOffenseTeamId=1610612737,
            resolvedDefenseTeamId=1610612738,
            offenseHomeAway="h",
            defenseHomeAway="v",
            personId=203,
            shotActionNumber=10,
            shotValue=3,
            isRebound=True,
            isDreb=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="def_rebound",
        ),
        make_event(
            gameId="0022401000",
            actionNumber=12,
            orderNumber=200,
            period=2,
            actionType="period",
            subType="start",
            clock="PT12M00.00S",
            scoreHome=80,
            scoreAway=80,
            scoreMarginBefore=0,
            scoreMarginAfter=0,
            resolvedOffenseTeamId=1610612738,
            resolvedDefenseTeamId=1610612737,
            offenseHomeAway="v",
            defenseHomeAway="h",
        ),
        make_event(
            gameId="0022401000",
            actionNumber=13,
            orderNumber=210,
            period=2,
            actionType="2pt",
            clock="PT11M45.00S",
            scoreHome=80,
            scoreAway=82,
            scoreMarginBefore=0,
            scoreMarginAfter=2,
            resolvedOffenseTeamId=1610612738,
            resolvedDefenseTeamId=1610612737,
            offenseHomeAway="v",
            defenseHomeAway="h",
            shotValue=2,
            isMadeShot=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="made_shot",
        ),
    ]

    possession_rows = possessions_silver.build_possession_rows_from_events(rows)

    assert len(possession_rows) == 2

    first = possession_rows[0]
    assert first["possessionEndType"] == "def_rebound"
    assert first["possessionStartType"] == "off_deadball"

    second = possession_rows[1]
    assert second["period"] == 2
    assert second["possessionNumber"] == 2
    assert second["possessionNumberInPeriod"] == 1
    assert second["previousPossessionNumber"] is None
    assert second["startClock"] == "PT12M00.00S"
    assert second["possessionStartType"] == "off_deadball"
    assert second["pointsScoredOnPossession"] == 2


def test_build_possession_rows_from_events_marks_ft_make_start_type():
    rows = [
        make_event(actionNumber=1, orderNumber=100, actionType="period", subType="start"),
        make_event(
            actionNumber=2,
            orderNumber=110,
            actionType="freethrow",
            clock="PT11M50.00S",
            scoreHome=1,
            scoreAway=0,
            scoreMarginBefore=0,
            scoreMarginAfter=1,
            shotResult="Made",
            isFreeThrow=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="free_throw",
        ),
        make_event(
            actionNumber=3,
            orderNumber=120,
            actionType="turnover",
            clock="PT11M35.00S",
            scoreHome=1,
            scoreAway=0,
            scoreMarginBefore=-1,
            scoreMarginAfter=-1,
            resolvedOffenseTeamId=1610612738,
            resolvedDefenseTeamId=1610612737,
            offenseHomeAway="v",
            defenseHomeAway="h",
            teamId=1610612738,
            isTurnover=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="turnover",
        ),
    ]

    possession_rows = possessions_silver.build_possession_rows_from_events(rows)

    assert len(possession_rows) == 2
    assert possession_rows[1]["possessionStartType"] == "off_ft_make"


def test_build_possession_rows_from_events_excludes_non_real_offensive_rebounds():
    rows = [
        make_event(actionNumber=1, orderNumber=100, actionType="period", subType="start"),
        make_event(
            actionNumber=2,
            orderNumber=110,
            actionType="turnover",
            clock="PT11M50.00S",
            scoreHome=0,
            scoreAway=0,
            teamId=1610612737,
            isTurnover=True,
            isPossessionEndingEvent=False,
            countAsPossession=False,
            subType="shotclock",
        ),
        make_event(
            actionNumber=3,
            orderNumber=111,
            actionType="rebound",
            clock="PT11M50.00S",
            scoreHome=0,
            scoreAway=0,
            personId=0,
            shotActionNumber=None,
            isRebound=True,
            isOreb=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="offense_change",
        ),
    ]

    possession_rows = possessions_silver.build_possession_rows_from_events(rows)

    assert len(possession_rows) == 1
    assert possession_rows[0]["offensiveRebounds"] == 0


def test_build_possession_rows_from_events_excludes_buzzer_placeholder_team_oreb():
    rows = [
        make_event(
            gameId="0012000001",
            period=2,
            actionNumber=351,
            orderNumber=351,
            clock="PT00M00.30S",
            secondsRemainingInPeriod=0.3,
            actionType="3pt",
            personId=202696,
            teamId=1610612753,
            resolvedOffenseTeamId=1610612753,
            resolvedDefenseTeamId=1610612739,
            offenseHomeAway="h",
            defenseHomeAway="v",
            shotValue=3,
            isMissedShot=True,
        ),
        make_event(
            gameId="0012000001",
            period=2,
            actionNumber=352,
            orderNumber=352,
            clock="PT00M00.30S",
            secondsRemainingInPeriod=0.3,
            actionType="rebound",
            subType="offensive",
            personId=0,
            teamId=1610612753,
            resolvedOffenseTeamId=1610612753,
            resolvedDefenseTeamId=1610612739,
            offenseHomeAway="h",
            defenseHomeAway="v",
            shotActionNumber=351,
            isRebound=True,
            isOreb=True,
        ),
        make_event(
            gameId="0012000001",
            period=2,
            actionNumber=353,
            orderNumber=353,
            clock="PT00M00.00S",
            secondsRemainingInPeriod=0.0,
            actionType="period",
            subType="end",
            isPossessionEndingEvent=True,
            possessionBoundaryReason="period_end",
        ),
    ]

    possession_rows = possessions_silver.build_possession_rows_from_events(rows)

    assert len(possession_rows) == 1
    assert possession_rows[0]["offensiveRebounds"] == 0


def test_build_possession_rows_from_events_keeps_oreb_end_type_distinct_from_boundary_reason():
    rows = [
        make_event(actionNumber=1, orderNumber=100, actionType="period", subType="start"),
        make_event(
            actionNumber=2,
            orderNumber=110,
            actionType="freethrow",
            clock="PT01M22.00S",
            scoreHome=10,
            scoreAway=8,
            scoreMarginBefore=2,
            scoreMarginAfter=3,
            shotResult="Made",
            isFreeThrow=True,
        ),
        make_event(
            actionNumber=3,
            orderNumber=120,
            actionType="rebound",
            clock="PT01M22.00S",
            scoreHome=10,
            scoreAway=8,
            scoreMarginBefore=3,
            scoreMarginAfter=3,
            personId=12,
            isRebound=True,
            isOreb=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="def_rebound",
        ),
    ]

    possession_rows = possessions_silver.build_possession_rows_from_events(rows)

    assert len(possession_rows) == 1
    assert possession_rows[0]["possessionEndType"] == "rebound"


def test_build_possession_rows_from_events_recomputes_end_margin_from_possession_offense():
    rows = [
        make_event(
            actionNumber=1,
            orderNumber=100,
            period=2,
            actionType="period",
            subType="start",
            scoreHome=24,
            scoreAway=26,
            scoreMarginBefore=-2,
            scoreMarginAfter=-2,
        ),
        make_event(
            actionNumber=2,
            orderNumber=110,
            period=2,
            actionType="3pt",
            clock="PT11M51.00S",
            scoreHome=24,
            scoreAway=26,
            scoreMarginBefore=-2,
            scoreMarginAfter=2,
            resolvedOffenseTeamId=1610612740,
            resolvedDefenseTeamId=1610612754,
            offenseHomeAway="h",
            defenseHomeAway="v",
            teamId=1610612754,
            shotValue=3,
            isMissedShot=True,
        ),
        make_event(
            actionNumber=3,
            orderNumber=120,
            period=2,
            actionType="rebound",
            clock="PT11M46.00S",
            scoreHome=24,
            scoreAway=26,
            scoreMarginBefore=2,
            scoreMarginAfter=2,
            resolvedOffenseTeamId=1610612754,
            resolvedDefenseTeamId=1610612740,
            offenseHomeAway="v",
            defenseHomeAway="h",
            personId=10,
            shotActionNumber=2,
            isRebound=True,
            isDreb=True,
            isPossessionEndingEvent=True,
            countAsPossession=True,
            possessionBoundaryReason="def_rebound",
        ),
    ]

    possession_rows = possessions_silver.build_possession_rows_from_events(rows)

    assert len(possession_rows) == 1
    assert possession_rows[0]["startScoreMargin"] == -2
    assert possession_rows[0]["endScoreMargin"] == -2


def test_build_possession_rows_from_payload_uses_pbpstats_possessions(monkeypatch):
    class FakeFieldGoal:
        def __init__(self, *, event_num, order, clock, score, is_made):
            self.event_num = event_num
            self.order = order
            self.clock = clock
            self.score = score
            self.is_made = is_made
            self.is_possession_ending_event = True
            self.count_as_possession = True
            self.action_type = "2pt"
            self.sub_type = None

        def is_second_chance_event(self):
            return False

        def is_penalty_event(self):
            return False

    class FakeTurnover:
        def __init__(self, *, event_num, order, clock, score):
            self.event_num = event_num
            self.order = order
            self.clock = clock
            self.score = score
            self.is_possession_ending_event = True
            self.count_as_possession = True
            self.action_type = "turnover"
            self.sub_type = None

        def is_second_chance_event(self):
            return False

        def is_penalty_event(self):
            return False

    class FakeStartEvent:
        def __init__(self, *, event_num, order, clock, score):
            self.event_num = event_num
            self.order = order
            self.clock = clock
            self.score = score
            self.is_possession_ending_event = False
            self.count_as_possession = False
            self.action_type = "period"
            self.sub_type = "start"

        def is_second_chance_event(self):
            return False

        def is_penalty_event(self):
            return False

    monkeypatch.setattr(possessions_silver, "FieldGoal", FakeFieldGoal)
    monkeypatch.setattr(possessions_silver, "Turnover", FakeTurnover)

    start_event = FakeStartEvent(
        event_num=1,
        order=100,
        clock="PT12M00.00S",
        score={1610612737: 0, 1610612738: 0},
    )
    first_event = FakeFieldGoal(
        event_num=2,
        order=110,
        clock="PT11M40.00S",
        score={1610612737: 2, 1610612738: 0},
        is_made=True,
    )
    second_event = FakeTurnover(
        event_num=4,
        order=130,
        clock="PT11M10.00S",
        score={1610612737: 2, 1610612738: 0},
    )

    possession_one = SimpleNamespace(
        events=[start_event, first_event],
        previous_possession=None,
        next_possession=None,
        number=1,
        period=1,
        offense_team_id=1610612737,
        start_time="PT12M00.00S",
        end_time="PT11M40.00S",
        start_score_margin=0,
        possession_has_timeout=False,
        previous_possession_has_timeout=False,
        possession_start_type="OffDeadball",
    )
    possession_two = SimpleNamespace(
        events=[second_event],
        previous_possession=possession_one,
        next_possession=None,
        number=2,
        period=1,
        offense_team_id=1610612738,
        start_time="PT11M40.00S",
        end_time="PT11M10.00S",
        start_score_margin=-2,
        possession_has_timeout=True,
        previous_possession_has_timeout=False,
        possession_start_type="OffTimeout",
    )
    possession_one.next_possession = possession_two

    def fake_load_live_possession_items(payload, *, fallback_game_id=None):
        return fallback_game_id or "0022400999", [possession_one, possession_two]

    monkeypatch.setattr(
        possessions_silver,
        "load_live_possession_items",
        fake_load_live_possession_items,
    )

    rows = possessions_silver.build_possession_rows_from_payload(
        payload={"game": {"gameId": "0022400999"}},
        playbyplay_rows=[
            make_event(
                actionNumber=2,
                orderNumber=110,
                clock="PT11M40.00S",
                timeActual="2024-01-01T00:00:20Z",
                scoreHome=2,
                scoreAway=0,
                offenseHomeAway="h",
                defenseHomeAway="v",
                resolvedOffenseTeamId=1610612737,
                resolvedDefenseTeamId=1610612738,
                isMadeShot=True,
                isPossessionEndingEvent=True,
                countAsPossession=True,
                possessionBoundaryReason="made_shot",
            ),
            make_event(
                actionNumber=4,
                orderNumber=130,
                clock="PT11M10.00S",
                timeActual="2024-01-01T00:00:50Z",
                scoreHome=2,
                scoreAway=0,
                offenseHomeAway="v",
                defenseHomeAway="h",
                resolvedOffenseTeamId=1610612738,
                resolvedDefenseTeamId=1610612737,
                isTurnover=True,
                isPossessionEndingEvent=True,
                countAsPossession=True,
                possessionBoundaryReason="turnover",
            ),
        ],
        fallback_game_id="0022400999",
    )

    assert len(rows) == 2
    assert rows[0]["countsAsPossession"] is True
    assert rows[0]["possessionStartType"] == "off_deadball"
    assert rows[0]["possessionEndType"] == "made_shot"
    assert rows[0]["pointsScoredOnPossession"] == 2
    assert rows[1]["previousPossessionNumber"] == 1
    assert rows[1]["previousPossessionEndingActionNumber"] == 2
    assert rows[1]["possessionStartType"] == "off_timeout"
    assert rows[1]["possessionEndType"] == "turnover"


def test_stamp_lineup_context_assigns_lineup_ids_for_single_stint_overlap():
    possession_rows = [
        {
            "gameId": "0022401111",
            "period": 1,
            "startOrderNumber": 100,
            "endOrderNumber": 150,
            "homeLineupId": None,
            "awayLineupId": None,
            "lineupValidFlag": None,
            "lineupIssue": None,
        }
    ]
    on_court_rows = [
        {
            "gameId": "0022401111",
            "period": 1,
            "stint_id": 1,
            "start_orderNumber": 0,
            "end_orderNumber": 200,
            "home_personIds": [1, 2, 3, 4, 5],
            "away_personIds": [6, 7, 8, 9, 10],
            "lineup_valid_flag": 1,
            "lineup_issue": None,
        }
    ]

    stamped = possessions_silver.stamp_lineup_context(possession_rows, on_court_rows)

    assert stamped[0]["homeLineupId"] == "1-2-3-4-5"
    assert stamped[0]["awayLineupId"] == "10-6-7-8-9"
    assert stamped[0]["lineupValidFlag"] == 1
    assert stamped[0]["lineupIssue"] is None


def test_stamp_lineup_context_marks_cross_stint_possession_as_invalid_when_lineups_change():
    possession_rows = [
        {
            "gameId": "0022401112",
            "period": 1,
            "startOrderNumber": 100,
            "endOrderNumber": 180,
            "homeLineupId": None,
            "awayLineupId": None,
            "lineupValidFlag": None,
            "lineupIssue": None,
        }
    ]
    on_court_rows = [
        {
            "gameId": "0022401112",
            "period": 1,
            "stint_id": 1,
            "start_orderNumber": 0,
            "end_orderNumber": 140,
            "home_personIds": [1, 2, 3, 4, 5],
            "away_personIds": [6, 7, 8, 9, 10],
            "lineup_valid_flag": 1,
            "lineup_issue": None,
        },
        {
            "gameId": "0022401112",
            "period": 1,
            "stint_id": 2,
            "start_orderNumber": 140,
            "end_orderNumber": 220,
            "home_personIds": [1, 2, 3, 4, 11],
            "away_personIds": [6, 7, 8, 9, 10],
            "lineup_valid_flag": 1,
            "lineup_issue": None,
        },
    ]

    stamped = possessions_silver.stamp_lineup_context(possession_rows, on_court_rows)

    assert stamped[0]["homeLineupId"] is None
    assert stamped[0]["awayLineupId"] == "10-6-7-8-9"
    assert stamped[0]["lineupValidFlag"] == 0
    assert stamped[0]["lineupIssue"] == "multiple_home_lineups(count=2)"


def test_stamp_lineup_context_collapses_same_clock_substitution_micro_stints_to_final_lineup():
    possession_rows = [
        {
            "gameId": "0022401113",
            "period": 1,
            "startOrderNumber": 80,
            "endOrderNumber": 97,
            "startClock": "PT04M51.00S",
            "homeLineupId": None,
            "awayLineupId": None,
            "lineupValidFlag": None,
            "lineupIssue": None,
        }
    ]
    on_court_rows = [
        {
            "gameId": "0022401113",
            "period": 1,
            "stint_id": 2,
            "start_orderNumber": 80,
            "end_orderNumber": 82,
            "start_clock": "PT04M51.00S",
            "home_personIds": [200782, 201950, 203114, 203507, 1626192],
            "away_personIds": [101108, 203109, 1626164, 1628969, 1629028],
            "lineup_valid_flag": 1,
            "lineup_issue": None,
        },
        {
            "gameId": "0022401113",
            "period": 1,
            "stint_id": 3,
            "start_orderNumber": 82,
            "end_orderNumber": 98,
            "start_clock": "PT04M51.00S",
            "home_personIds": [200782, 201950, 203114, 1626171, 1626192],
            "away_personIds": [101108, 203109, 1626164, 1628969, 1629028],
            "lineup_valid_flag": 1,
            "lineup_issue": None,
        },
    ]

    stamped = possessions_silver.stamp_lineup_context(possession_rows, on_court_rows)

    assert stamped[0]["homeLineupId"] == "1626171-1626192-200782-201950-203114"
    assert stamped[0]["awayLineupId"] == "101108-1626164-1628969-1629028-203109"
    assert stamped[0]["lineupValidFlag"] == 1
    assert stamped[0]["lineupIssue"] is None
