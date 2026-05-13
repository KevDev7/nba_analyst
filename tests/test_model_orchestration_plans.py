from __future__ import annotations

import unittest

from pydantic import ValidationError

from apps.assistant.model_orchestration.planner import dry_run_payload
from apps.assistant.model_orchestration.plans import ModelAnalysisPlan, planned_tool_names


class ModelOrchestrationPlanTests(unittest.TestCase):
    def test_valid_period_delta_plan_parses_with_governed_tools(self) -> None:
        plan = ModelAnalysisPlan(
            plan={
                "kind": "period_delta",
                "subject": "teams",
                "measure": "average points",
                "periods": [
                    {"season": "2023-24", "season_type": "regular_season"},
                    {"season": "2024-25", "season_type": "regular_season"},
                ],
                "join_key": "entity",
                "delta": "right_minus_left",
            },
            tool_sequence=[
                {"tool_name": "semantic_query.plan_execute", "purpose": "left period retrieval"},
                {"tool_name": "semantic_query.plan_execute", "purpose": "right period retrieval"},
                {"tool_name": "python_analysis.run", "purpose": "compute delta"},
                {"tool_name": "artifact_renderer.render", "purpose": "render artifacts"},
            ],
        )

        self.assertEqual(plan.plan.kind, "period_delta")
        self.assertEqual(
            planned_tool_names(plan),
            [
                "semantic_query.plan_execute",
                "semantic_query.plan_execute",
                "python_analysis.run",
                "artifact_renderer.render",
            ],
        )

    def test_valid_correlation_plan_parses_with_governed_tools(self) -> None:
        plan = ModelAnalysisPlan(
            plan={
                "kind": "correlation",
                "subject": "players",
                "x_measure": "average points",
                "y_measure": "average assists",
                "period": {"season": "2024-25", "season_type": "regular_season"},
                "join_key": "entity",
                "method": "pearson",
            },
            tool_sequence=[
                {"tool_name": "semantic_query.plan_execute", "purpose": "x metric retrieval"},
                {"tool_name": "semantic_query.plan_execute", "purpose": "y metric retrieval"},
                {"tool_name": "python_analysis.run", "purpose": "compute correlation"},
                {"tool_name": "artifact_renderer.render", "purpose": "render artifacts"},
            ],
        )

        self.assertEqual(plan.plan.kind, "correlation")
        self.assertEqual(
            planned_tool_names(plan),
            [
                "semantic_query.plan_execute",
                "semantic_query.plan_execute",
                "python_analysis.run",
                "artifact_renderer.render",
            ],
        )

    def test_forbidden_raw_sql_tool_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ModelAnalysisPlan(
                plan={"kind": "simple_semantic_query", "question": "Show top teams"},
                tool_sequence=[{"tool_name": "raw_sql", "purpose": "query database"}],
            )

    def test_forbidden_raw_python_reference_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ModelAnalysisPlan(
                plan={"kind": "simple_semantic_query", "question": "Use python_code to analyze teams"},
                tool_sequence=[{"tool_name": "semantic_query.plan_execute", "purpose": "retrieve"}],
            )

        with self.assertRaises(ValidationError):
            ModelAnalysisPlan(
                plan={"kind": "simple_semantic_query", "question": "Use arbitrary_python to analyze teams"},
                tool_sequence=[{"tool_name": "semantic_query.plan_execute", "purpose": "retrieve"}],
            )

    def test_unsupported_surface_must_use_unsupported_plan(self) -> None:
        with self.assertRaises(ValidationError):
            ModelAnalysisPlan(
                plan={"kind": "simple_semantic_query", "question": "Show lineup on-off stats"},
                tool_sequence=[{"tool_name": "semantic_query.plan_execute", "purpose": "retrieve"}],
            )

        plan = ModelAnalysisPlan(
            plan={"kind": "unsupported", "reason": "Lineup data is not exposed by the ontology.", "unsupported_surface": "lineups"},
            tool_sequence=[],
        )
        self.assertEqual(plan.plan.kind, "unsupported")

    def test_dry_run_payload_is_not_auto_executed(self) -> None:
        plan = ModelAnalysisPlan(
            plan={"kind": "simple_semantic_query", "question": "Show top teams by net rating"},
            tool_sequence=[{"tool_name": "semantic_query.plan_execute", "purpose": "retrieve"}],
        )

        payload = dry_run_payload("Show top teams by net rating", plan)

        self.assertFalse(payload["auto_executed"])
        self.assertEqual(payload["planned_tool_sequence"], ["semantic_query.plan_execute"])

    def test_plan_rejects_too_many_tool_steps(self) -> None:
        with self.assertRaises(ValidationError):
            ModelAnalysisPlan(
                plan={"kind": "simple_semantic_query", "question": "Show top teams"},
                tool_sequence=[
                    {"tool_name": "semantic_query.plan_execute", "purpose": f"step {index}"}
                    for index in range(9)
                ],
            )


if __name__ == "__main__":
    unittest.main()
