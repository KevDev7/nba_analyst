from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.assistant.pipeline import AssistantResult
from apps.cli.main import plan_question, run_cli


SAMPLE_DRAFT = {
    "task": "rank",
    "subject": "players",
    "measure": "points",
    "time_window": {"kind": "last_n_games", "value": 10},
    "limit": 10,
    "sort": "desc",
    "assumptions": [],
}

SAMPLE_EXECUTION_PLAN = {
    "plan_type": "single_sql",
    "query_kind": "metric_query",
    "result_shape": "ranking",
    "entity_label_singular": "Player",
    "entity_label_plural": "Players",
    "context_label": "Team",
    "metric": "total_points",
    "metric_aggregation": "sum",
    "window_games": 10,
    "time_grain": None,
    "time_filter": None,
    "season_label": None,
    "season_type": None,
    "limit": 10,
    "assumptions": [],
    "steps": [{"kind": "run_sql", "sql": "SELECT 1", "analysis_spec": None}],
}


class CliPipelineTests(unittest.TestCase):
    @patch("apps.cli.main.run_assistant", return_value=AssistantResult(answer="formatted output"))
    def test_cli_path_renders_shared_assistant_answer(self, mock_run_assistant) -> None:
        output = run_cli("Show me the top 10 players by points over the last 10 games")

        self.assertEqual(output, "formatted output")
        mock_run_assistant.assert_called_once_with(
            "Show me the top 10 players by points over the last 10 games",
            debug=False,
        )

    @patch("apps.cli.main.run_assistant", side_effect=RuntimeError("bad semantic draft"))
    def test_cli_path_has_no_silent_fallback(self, mock_run_assistant) -> None:
        with self.assertRaises(RuntimeError) as context:
            run_cli("Show me the top 10 players by points over the last 10 games")

        self.assertIn("bad semantic draft", str(context.exception))
        mock_run_assistant.assert_called_once()

    @patch(
        "apps.cli.main.run_assistant",
        return_value=AssistantResult(
            answer="formatted output",
            debug={
                "query_type": "metric_query",
                "semantic_draft": SAMPLE_DRAFT,
                "query": {"kind": "MetricQuery"},
                "resolved_query": {"kind": "ResolvedMetric"},
                "execution_plan": SAMPLE_EXECUTION_PLAN,
                "answer": "formatted output",
            },
        ),
    )
    def test_cli_debug_renders_shared_assistant_debug_payload(self, mock_run_assistant) -> None:
        output = run_cli(
            "Show me the top 10 players by points over the last 10 games",
            debug=True,
        )

        self.assertIn("Query type: metric_query", output)
        self.assertIn("Semantic draft:", output)
        self.assertIn("Execution plan:", output)
        self.assertTrue(output.endswith("formatted output"))
        mock_run_assistant.assert_called_once_with(
            "Show me the top 10 players by points over the last 10 games",
            debug=True,
        )

    @patch(
        "apps.assistant.pipeline.call_haskell_planner_for_semantic_draft",
        return_value={"execution_plan": SAMPLE_EXECUTION_PLAN},
    )
    @patch("apps.assistant.pipeline.interpret_question_to_semantic_draft", return_value=SAMPLE_DRAFT)
    def test_plan_question_bridges_draft_interpreter_to_haskell_draft_planner(
        self,
        mock_interpret,
        mock_draft_planner,
    ) -> None:
        semantic_draft, planner_output = plan_question(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(semantic_draft, SAMPLE_DRAFT)
        self.assertEqual(planner_output, {"execution_plan": SAMPLE_EXECUTION_PLAN})
        mock_interpret.assert_called_once_with(
            "Show me the top 10 players by points over the last 10 games"
        )
        mock_draft_planner.assert_called_once_with(SAMPLE_DRAFT)


if __name__ == "__main__":
    unittest.main()
