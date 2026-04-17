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
# Next:
# - future grouped aggregations and linked-filter slices

from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner, run_cli


class SliceEightTests(unittest.TestCase):
    def test_monthly_average_points_trend_query(self) -> None:
        planner_output = call_haskell_planner(
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

    def test_monthly_average_points_trend_output(self) -> None:
        output = run_cli("What are the monthly average points over the past year?")
        self.assertIn("Monthly average points over the past year are shown below.", output)
        self.assertIn("Month | Average Points", output)

    def test_monthly_average_points_by_team_trend_query(self) -> None:
        planner_output = call_haskell_planner(
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

    def test_monthly_average_points_by_team_trend_output(self) -> None:
        output = run_cli("What are the monthly average points by team over the past year?")
        self.assertIn("Monthly average points by team over the past year are shown below.", output)
        self.assertIn("Month | Team | Average Points", output)

    def test_last_month_trend_is_still_unsupported(self) -> None:
        with self.assertRaises(RuntimeError):
            run_cli("What is the trend in points over the last month?")


if __name__ == "__main__":
    unittest.main()
