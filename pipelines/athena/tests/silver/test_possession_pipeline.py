from __future__ import annotations

import sys
from pathlib import Path


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

from pbpstats_projection_common import InvalidNumberOfStartersException
from possessions.inputs import PossessionGameInput
from possessions.pipeline import PbpstatsPossessionPipeline


def make_game_input() -> PossessionGameInput:
    return PossessionGameInput(
        game_id="0022400999",
        payload={"game": {"gameId": "0022400999", "actions": []}},
        playbyplay_rows=[],
        on_court_rows=[],
        source_key="raw/cdn/playbyplay/game_id=0022400999.json",
    )


def test_build_exact_game_returns_exact_written_candidate(monkeypatch):
    pipeline = PbpstatsPossessionPipeline()
    monkeypatch.setattr(
        "possessions.pipeline.build_possession_rows_from_payload",
        lambda *args, **kwargs: [{"gameId": "0022400999", "possessionNumber": 1}],
    )

    result = pipeline.build_exact_game(make_game_input())

    assert result.status == "exact_written_candidate"
    assert result.rows.rows == [{"gameId": "0022400999", "possessionNumber": 1}]


def test_build_exact_game_classifies_reference_failure(monkeypatch):
    pipeline = PbpstatsPossessionPipeline()

    def raise_starter_failure(*args, **kwargs):
        raise InvalidNumberOfStartersException("GameId: 0022400999, Period: 5, TeamId: 1, Players: []")

    monkeypatch.setattr(
        "possessions.pipeline.build_possession_rows_from_payload",
        raise_starter_failure,
    )

    result = pipeline.build_exact_game(make_game_input())

    assert result.status == "unresolved"
    assert result.reference_failure_type == "InvalidNumberOfStartersException"
    assert result.reference_failure_period == 5


def test_build_ot_fallback_game_returns_fallback_written_candidate(monkeypatch):
    pipeline = PbpstatsPossessionPipeline()

    def raise_starter_failure(*args, **kwargs):
        raise InvalidNumberOfStartersException("GameId: 0022400999, Period: 5, TeamId: 1, Players: []")

    monkeypatch.setattr(
        "possessions.pipeline.build_possession_rows_from_payload",
        raise_starter_failure,
    )
    monkeypatch.setattr(
        "possessions.pipeline.build_fallback_rows_for_game",
        lambda *args, **kwargs: (
            [{"gameId": "0022400999", "possessionNumber": 1}],
            5,
            True,
            "fallback_ot_end_q4_drift_reconcile",
        ),
    )

    result = pipeline.build_ot_fallback_game(make_game_input())

    assert result.status == "fallback_written_candidate"
    assert result.reference_failure_period == 5
    assert result.possession_source_method == "fallback_ot_end_q4_drift_reconcile"
    assert result.opening_subcluster_applied is True


def test_build_ot_fallback_game_stays_unresolved_when_no_family_applies(monkeypatch):
    pipeline = PbpstatsPossessionPipeline()

    def raise_starter_failure(*args, **kwargs):
        raise InvalidNumberOfStartersException("GameId: 0022400999, Period: 5, TeamId: 1, Players: []")

    monkeypatch.setattr(
        "possessions.pipeline.build_possession_rows_from_payload",
        raise_starter_failure,
    )
    monkeypatch.setattr(
        "possessions.pipeline.build_fallback_rows_for_game",
        lambda *args, **kwargs: None,
    )

    result = pipeline.build_ot_fallback_game(make_game_input())

    assert result.status == "unresolved"
    assert result.reference_failure_type == "InvalidNumberOfStartersException"
    assert result.reference_failure_period == 5


def test_build_ot_fallback_game_skips_when_exact_possessions_load(monkeypatch):
    pipeline = PbpstatsPossessionPipeline()
    monkeypatch.setattr(
        "possessions.pipeline.build_possession_rows_from_payload",
        lambda *args, **kwargs: [{"gameId": "0022400999", "possessionNumber": 1}],
    )

    result = pipeline.build_ot_fallback_game(make_game_input())

    assert result.status == "skipped"
    assert result.warning_details == "pbpstats_possessions_loaded_without_fallback"
