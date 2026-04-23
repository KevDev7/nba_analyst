from __future__ import annotations

import unittest
from unittest.mock import patch

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


class SliceTenTests(unittest.TestCase):
    @patch("apps.cli.main.format_response", return_value="formatted output")
    @patch("apps.cli.main.synthesize_answer", return_value={"summary": "ok"})
    @patch("apps.cli.main.package_results", return_value={"packaged": True})
    @patch("apps.cli.main.execute_plan", return_value={"runtime": True})
    @patch(
        "apps.cli.main.plan_question",
        return_value=(SAMPLE_DRAFT, {"execution_plan": SAMPLE_EXECUTION_PLAN}),
    )
    @patch("apps.cli.main.load_database")
    def test_live_cli_path_uses_semantic_draft_then_runtime(
        self,
        mock_load_database,
        mock_plan_question,
        mock_execute_plan,
        mock_package_results,
        mock_synthesize_answer,
        mock_format_response,
    ) -> None:
        output = run_cli("Show me the top 10 players by points over the last 10 games")

        self.assertEqual(output, "formatted output")
        mock_load_database.assert_called_once_with()
        mock_plan_question.assert_called_once_with(
            "Show me the top 10 players by points over the last 10 games"
        )
        mock_execute_plan.assert_called_once()
        mock_package_results.assert_called_once_with({"runtime": True})
        mock_synthesize_answer.assert_called_once_with({"packaged": True})
        mock_format_response.assert_called_once_with({"summary": "ok"})

    @patch("apps.cli.main.load_database")
    @patch(
        "apps.cli.main.plan_question",
        side_effect=RuntimeError("bad semantic draft"),
    )
    def test_live_cli_path_has_no_silent_fallback(self, mock_plan_question, mock_load_database) -> None:
        with self.assertRaises(RuntimeError) as context:
            run_cli("Show me the top 10 players by points over the last 10 games")

        self.assertIn("bad semantic draft", str(context.exception))
        mock_load_database.assert_called_once_with()
        mock_plan_question.assert_called_once()

    @patch(
        "apps.cli.main.call_haskell_planner_for_semantic_draft",
        return_value={"execution_plan": SAMPLE_EXECUTION_PLAN},
    )
    @patch("apps.cli.main.interpret_question_to_semantic_draft", return_value=SAMPLE_DRAFT)
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
