# Purpose:
# Verify the first time-semantic trend slice over semantic_gold.
#
# Uses:
# - the CLI entrypoint
# - the Haskell semantic core
# - the generated ontology fixture
#
# Produces:
# - regression coverage for monthly trend analysis over the past year
#
from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.cli.main import plan_question, run_cli


def _trend_gemini_response(prompt: str) -> str:
    marker = "User question:\n"
    if marker not in prompt:
        raise AssertionError(f"Unexpected trend prompt shape: {prompt}")
    question = prompt.split(marker, 1)[1].split("\n\nReturn the JSON response now.", 1)[0]

    if question == "What are the monthly average points over the past year?":
        return """
        {
          "status": "ok",
          "draft": {
            "task": "trend",
            "subject": "teams",
            "measure": "average points",
            "measures": ["average points"],
            "dimensions": [],
            "filters": [],
            "time_window": {"kind": "past_year", "value": null},
            "grain": "month",
            "order": [],
            "limit": null,
            "sort": null,
            "entities": [],
            "operations": [],
            "assumptions": []
          }
        }
        """
    if question == "What are the monthly average points by team over the past year?":
        return """
        {
          "status": "ok",
          "draft": {
            "task": "trend",
            "subject": "teams",
            "measure": "average points",
            "measures": ["average points"],
            "dimensions": ["team"],
            "filters": [],
            "time_window": {"kind": "past_year", "value": null},
            "grain": "month",
            "order": [],
            "limit": null,
            "sort": null,
            "entities": [],
            "operations": [],
            "assumptions": []
          }
        }
        """
    if question == "What is the trend in points over the last month?":
        return """
        {
          "status": "ok",
          "draft": {
            "task": "trend",
            "subject": "teams",
            "measure": "points",
            "measures": ["points"],
            "dimensions": [],
            "filters": [],
            "time_window": {"kind": "last_month", "value": 1},
            "grain": "day",
            "order": [],
            "limit": null,
            "sort": null,
            "entities": [],
            "operations": [],
            "assumptions": []
          }
        }
        """
    raise AssertionError(f"Unexpected trend prompt: {prompt}")


class SliceEightTests(unittest.TestCase):
    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_monthly_average_points_trend_query(self, mock_call_gemini) -> None:
        mock_call_gemini.side_effect = _trend_gemini_response
        _interpreted_query, planner_output = plan_question(
            "What are the monthly average points over the past year?"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], [])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(shared["filters"], [{"kind": "past_year"}])

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["factTableName"], "team_game")
        self.assertIsNone(resolved["seriesPath"])
        self.assertIsNone(resolved["seriesName"])
        self.assertEqual(resolved["timeGrain"], "month")
        self.assertEqual(resolved["timeFilterKind"], "past_year")
        self.assertIn("STRFTIME({fact_alias}.game_date, '%Y-%m')", resolved["timeBucketExpression"])
        self.assertEqual(planner_output["execution_plan"]["result_shape"], "time_series")

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_monthly_average_points_trend_output(self, mock_call_gemini) -> None:
        mock_call_gemini.side_effect = _trend_gemini_response
        output = run_cli("What are the monthly average points over the past year?")
        self.assertIn("Monthly average points over the past year are shown below.", output)
        self.assertIn("Month | Average Points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_monthly_average_points_by_team_trend_query(self, mock_call_gemini) -> None:
        mock_call_gemini.side_effect = _trend_gemini_response
        _interpreted_query, planner_output = plan_question(
            "What are the monthly average points by team over the past year?"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(shared["filters"], [{"kind": "past_year"}])

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["seriesObjectName"], "Team")
        self.assertEqual(resolved["seriesPath"]["targetObjectName"], "Team")
        self.assertEqual(resolved["seriesPath"]["steps"][0]["linkName"], "team_game_team")
        self.assertEqual(resolved["seriesName"]["columnName"], "team_name")
        self.assertEqual(planner_output["execution_plan"]["result_shape"], "time_series")

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_monthly_average_points_by_team_trend_output(self, mock_call_gemini) -> None:
        mock_call_gemini.side_effect = _trend_gemini_response
        output = run_cli("What are the monthly average points by team over the past year?")
        self.assertIn("Monthly average points by team over the past year are shown below.", output)
        self.assertIn("Month | Team | Average Points", output)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_last_month_trend_is_outside_supported_trend_filters(self, mock_call_gemini) -> None:
        mock_call_gemini.side_effect = _trend_gemini_response
        with self.assertRaises(RuntimeError):
            run_cli("What is the trend in points over the last month?")


if __name__ == "__main__":
    unittest.main()
