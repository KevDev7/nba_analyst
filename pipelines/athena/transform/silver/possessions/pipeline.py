from __future__ import annotations

from pbpstats_projection_common import InvalidNumberOfStartersException

from .exact import build_possession_rows_from_payload
from .fallback import build_fallback_rows_for_game, parse_failed_period
from .inputs import PossessionGameInput
from .result import PossessionArtifactRows, PossessionBuildResult


class PbpstatsPossessionPipeline:
    def build_exact_game(self, game_input: PossessionGameInput) -> PossessionBuildResult:
        if game_input.game_id is None:
            return PossessionBuildResult(
                status="unresolved",
                warning_details="Missing fallback game_id from source key",
            )
        try:
            rows = build_possession_rows_from_payload(
                game_input.payload,
                game_input.playbyplay_rows,
                fallback_game_id=game_input.game_id,
                on_court_rows=game_input.on_court_rows,
            )
        except Exception as exc:
            failed_period = None
            if isinstance(exc, InvalidNumberOfStartersException):
                failed_period = parse_failed_period(exc)
            return PossessionBuildResult(
                status="unresolved",
                rows=PossessionArtifactRows(rows=[]),
                reference_failure_type=type(exc).__name__,
                reference_failure_period=failed_period,
                warning_details=f"{type(exc).__name__}: {exc}",
            )
        if not rows:
            return PossessionBuildResult(
                status="skipped",
                rows=PossessionArtifactRows(rows=[]),
                warning_details="empty_possessions",
            )
        return PossessionBuildResult(
            status="exact_written_candidate",
            rows=PossessionArtifactRows(rows=rows),
        )

    def build_ot_fallback_game(self, game_input: PossessionGameInput) -> PossessionBuildResult:
        if game_input.game_id is None:
            return PossessionBuildResult(
                status="unresolved",
                warning_details="Missing fallback game_id from source key",
            )
        try:
            build_possession_rows_from_payload(
                game_input.payload,
                game_input.playbyplay_rows,
                fallback_game_id=game_input.game_id,
                on_court_rows=game_input.on_court_rows,
            )
        except InvalidNumberOfStartersException as exc:
            fallback_result = build_fallback_rows_for_game(
                game_input.payload,
                game_input.playbyplay_rows,
                game_input.on_court_rows,
                reference_failure=exc,
            )
            if fallback_result is None:
                failed_period = parse_failed_period(exc)
                return PossessionBuildResult(
                    status="unresolved",
                    reference_failure_type=type(exc).__name__,
                    reference_failure_period=failed_period,
                    warning_details=f"{type(exc).__name__}: {exc}",
                )
            rows, failed_period, opening_cluster_applied, source_method = fallback_result
            return PossessionBuildResult(
                status="fallback_written_candidate",
                rows=PossessionArtifactRows(rows=rows),
                reference_failure_type="InvalidNumberOfStartersException",
                reference_failure_period=failed_period,
                possession_source_method=source_method,
                opening_subcluster_applied=opening_cluster_applied,
            )
        except Exception as exc:
            return PossessionBuildResult(
                status="unresolved",
                reference_failure_type=type(exc).__name__,
                warning_details=f"{type(exc).__name__}: {exc}",
            )
        return PossessionBuildResult(
            status="skipped",
            warning_details="pbpstats_possessions_loaded_without_fallback",
        )
