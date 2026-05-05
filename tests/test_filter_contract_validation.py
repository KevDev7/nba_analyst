from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class FilterContractValidationTests(unittest.TestCase):
    def test_supported_recent_metric_query_plans_with_filter_refs(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        shared = planner_output["query"]["spec"]["sharedQuery"]

        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(planner_output["resolved_query"]["resolved"]["windowGames"], 10)

    def test_supported_season_metric_query_plans_with_filter_refs(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeasonTeam",
                    "metrics": ["points_per_game"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "orders": [{"kind": "desc", "metric": "points_per_game"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(resolved["seasonLabel"], "2025-26")
        self.assertEqual(resolved["seasonType"], "regular_season")

    def test_supported_recent_metric_query_can_be_scoped_to_exact_season(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "last_n_games", "value": 8},
                        {"kind": "exact_season", "value": "2024-25"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved = planner_output["resolved_query"]["resolved"]
        sql = planner_output["execution_plan"]["execution"]["steps"][0]["sql"]

        self.assertEqual(resolved["windowGames"], 8)
        self.assertEqual(resolved["seasonLabel"], "2024-25")
        self.assertEqual(resolved["seasonType"], "regular_season")
        self.assertIn("f.season_year = '2024-25'", sql)
        self.assertIn("f.season_type = 'regular_season'", sql)
        self.assertIn("WHERE game_rank <= 8", sql)

    def test_supported_trend_query_plans_with_past_year_filter_ref(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name"],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["filters"],
            [{"kind": "past_year"}],
        )
        self.assertEqual(resolved["timeFilterKind"], "past_year")

    def test_unknown_filter_kind_fails_in_planner_not_ir_deserialization(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "made_up_filter", "value": "anything"}],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        message = str(context.exception)
        self.assertIn(
            "Metric queries require ontology-backed time filters",
            message,
        )
        self.assertNotIn("Unknown filter kind", message)

    def test_malformed_last_n_games_value_fails_at_contract_boundary(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": "ten"}],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn(
            "last_n_games filters require a positive integer value.",
            str(context.exception),
        )

    def test_missing_season_type_fails_with_season_bundle_message(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeasonTeam",
                    "metrics": ["points_per_game"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "exact_season", "value": "2025-26"}],
                    "orders": [{"kind": "desc", "metric": "points_per_game"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn(
            "Metric queries require ontology-backed time filters",
            str(context.exception),
        )

    def test_comparison_accepts_past_year_time_scope_filter_family(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "past_year"}],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": {
                    "kind": "compare_entities",
                    "targetObject": "Player",
                    "entities": [
                        {"entityId": 1628973, "entityName": "Jalen Brunson"},
                        {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    ],
                },
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved = planner_output["resolved_query"]["resolved"]
        plan = planner_output["execution_plan"]
        sql = plan["execution"]["steps"][0]["sql"]
        self.assertEqual(resolved["timeFilterKind"], "past_year")
        self.assertEqual(plan["answer_context"]["time"]["filter"], "past_year")
        self.assertIn("INTERVAL '1 year'", sql)

if __name__ == "__main__":
    unittest.main()
