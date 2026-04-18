from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact


class SliceTwentyThreeTests(unittest.TestCase):
    def test_supported_metric_query_still_plans_with_string_metric_ref(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_haskell_planner_for_query(payload)
        shared = planner_output["query"]["spec"]["sharedQuery"]

        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(
            planner_output["resolved_query"]["resolved"]["metricFormula"]["metricKey"],
            "average_points",
        )

    def test_metric_absent_from_ontology_fails_with_ontology_resolution_error(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["made_up_metric"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "made_up_metric"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn("Metric 'made_up_metric' not found in ontology.", str(context.exception))

    def test_non_executable_ontology_metric_fails_with_executability_error(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["points_per_36"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "points_per_36"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Metric 'points_per_36' is present in the ontology but not executable in this slice.",
            str(context.exception),
        )

    def test_comparison_now_accepts_average_points(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
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

        planner_output = call_haskell_planner_for_query(payload)
        self.assertEqual(planner_output["execution_plan"]["metric"], "average_points")
        self.assertEqual(planner_output["execution_plan"]["metric_aggregation"], "avg")

    def test_capability_artifact_still_contains_truthful_core_metric_families(self) -> None:
        artifact = _capability_artifact()

        matching = [
            family
            for family in artifact["families"]
            if family["family_key"] == "player_game_recent_metric"
        ]

        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["metrics"], ["average_points", "total_points"])
        self.assertNotIn("points_per_36", matching[0]["metrics"])


if __name__ == "__main__":
    unittest.main()
