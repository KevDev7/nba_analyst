from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.cli.main import ROOT, run_cli


SAMPLE_INTERPRETED_QUERY = {
    "kind": "metric_query",
    "spec": {
        "sharedQuery": {
            "coreFactObject": "PlayerGame",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "timeGrain": None,
            "filters": [{"kind": "last_n_games", "value": 10}],
            "linkedFilters": [],
            "orders": [{"kind": "desc", "metric": "total_points"}],
            "limit": 10,
            "assumptions": [],
        },
        "entityFilters": [],
        "comparison": None,
    },
}

SAMPLE_EXECUTION_PLAN = {
    "plan_type": "single_sql",
    "query_kind": "metric_query",
    "result_shape": "ranking",
    "entity_label_singular": "Player",
    "entity_label_plural": "Players",
    "context_label": "Team",
    "metric": "total_points",
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
        "apps.cli.main.call_haskell_planner_for_query",
        return_value={"execution_plan": SAMPLE_EXECUTION_PLAN},
    )
    @patch(
        "apps.cli.main.plan_question",
        return_value=(SAMPLE_INTERPRETED_QUERY, {"execution_plan": SAMPLE_EXECUTION_PLAN}),
    )
    @patch("apps.cli.main.load_database")
    def test_live_cli_path_uses_interpreter_then_plan_query_json(
        self,
        mock_load_database,
        mock_plan_question,
        mock_query_planner,
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
        mock_query_planner.assert_not_called()
        mock_execute_plan.assert_called_once()
        mock_package_results.assert_called_once_with({"runtime": True})
        mock_synthesize_answer.assert_called_once_with({"packaged": True})
        mock_format_response.assert_called_once_with({"summary": "ok"})

    @patch("apps.cli.main.load_database")
    @patch(
        "apps.cli.main.plan_question",
        side_effect=RuntimeError("bad structured output"),
    )
    @patch("apps.cli.main.call_haskell_planner_for_query")
    def test_live_cli_path_has_no_silent_fallback_to_legacy_question_planner(
        self,
        mock_query_planner,
        mock_plan_question,
        mock_load_database,
    ) -> None:
        with self.assertRaises(RuntimeError) as context:
            run_cli("Show me the top 10 players by points over the last 10 games")

        self.assertIn("bad structured output", str(context.exception))
        mock_load_database.assert_called_once_with()
        mock_plan_question.assert_called_once()
        mock_query_planner.assert_not_called()

    @patch("apps.cli.main.format_response", return_value="formatted output")
    @patch("apps.cli.main.synthesize_answer", return_value={"summary": "ok"})
    @patch("apps.cli.main.package_results", return_value={"packaged": True})
    @patch("apps.cli.main.execute_plan", return_value={"runtime": True})
    @patch("apps.cli.main.load_database")
    def test_haskell_receives_structured_query_json_not_raw_question_text(
        self,
        mock_load_database,
        mock_execute_plan,
        mock_package_results,
        mock_synthesize_answer,
        mock_format_response,
    ) -> None:
        captured_payloads: list[dict] = []

        def fake_plan_question(_question: str) -> tuple[dict, dict]:
            return SAMPLE_INTERPRETED_QUERY, {"execution_plan": SAMPLE_EXECUTION_PLAN}

        with patch(
            "apps.cli.main.plan_question",
            side_effect=fake_plan_question,
        ) as mock_plan_question:
            output = run_cli("Show me the top 10 players by points over the last 10 games")

        self.assertEqual(output, "formatted output")
        mock_load_database.assert_called_once_with()
        mock_plan_question.assert_called_once()
        mock_execute_plan.assert_called_once()
        mock_package_results.assert_called_once_with({"runtime": True})
        mock_synthesize_answer.assert_called_once_with({"packaged": True})
        mock_format_response.assert_called_once_with({"summary": "ok"})

    @patch("apps.cli.main.call_haskell_planner_for_query")
    @patch(
        "apps.cli.main.interpret_question_to_planner_query",
        return_value=SAMPLE_INTERPRETED_QUERY,
    )
    def test_plan_question_bridges_interpreter_to_query_planner(
        self,
        mock_interpret,
        mock_query_planner,
    ) -> None:
        from apps.cli.main import plan_question

        mock_query_planner.return_value = {"execution_plan": SAMPLE_EXECUTION_PLAN}

        interpreted_query, planner_output = plan_question(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(interpreted_query, SAMPLE_INTERPRETED_QUERY)
        self.assertEqual(planner_output, {"execution_plan": SAMPLE_EXECUTION_PLAN})
        mock_interpret.assert_called_once_with(
            "Show me the top 10 players by points over the last 10 games"
        )
        mock_query_planner.assert_called_once_with(SAMPLE_INTERPRETED_QUERY)

    def test_stale_haskell_question_front_end_modules_are_removed(self) -> None:
        for relative_path in [
            "services/ontology-hs/src/QueryModel/Interpret.hs",
            "services/ontology-hs/src/QueryModel/Match.hs",
            "services/ontology-hs/src/QueryModel/Classify.hs",
            "services/ontology-hs/src/QueryModel/Build.hs",
        ]:
            self.assertFalse((ROOT / relative_path).exists(), relative_path)

        main_contents = (
            ROOT / "services" / "ontology-hs" / "app" / "Main.hs"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"plan", "--ontology"', main_contents)
        self.assertNotIn("--question", main_contents)

        cli_contents = (ROOT / "apps" / "cli" / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("def call_haskell_planner(", cli_contents)


if __name__ == "__main__":
    unittest.main()
