from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner_for_query
from apps.cli.semantic_interpreter import _capability_artifact


class SliceTwentyFourTests(unittest.TestCase):
    def test_supported_metric_query_still_plans_with_string_dimension_ref(self) -> None:
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

        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(
            planner_output["resolved_query"]["resolved"]["displayName"]["columnName"],
            "player_name",
        )

    def test_nonexistent_dimension_fails_with_ontology_resolution_error(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["made_up_dimension"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
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
            "No valid ontology path from 'PlayerGame' reaches a displayed dimension attribute 'made_up_dimension'.",
            str(context.exception),
        )

    def test_wrong_kind_attribute_fails_with_attribute_kind_error(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["person_id"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
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
            "Attribute 'person_id' has the wrong kind in the ontology.",
            str(context.exception),
        )

    def test_comparison_still_only_accepts_player_name_dimension(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["display_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [
                    {"personId": 1628973, "playerName": "Jalen Brunson"},
                    {"personId": 1628369, "playerName": "Jayson Tatum"},
                ],
                "comparison": {
                    "kind": "compare_entities",
                    "entities": [
                        {"personId": 1628973, "playerName": "Jalen Brunson"},
                        {"personId": 1628369, "playerName": "Jayson Tatum"},
                    ],
                },
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn(
            "Comparison queries currently require the player_name dimension.",
            str(context.exception),
        )

    def test_trend_grouping_requires_reachable_public_dimension(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["display_name"],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "linkedFilters": [],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(payload)

        self.assertIn("No valid ontology path from 'TeamGame' reaches a displayed dimension attribute 'display_name'.", str(context.exception))

    def test_capability_artifact_still_contains_truthful_core_dimension_families(self) -> None:
        artifact = _capability_artifact()

        matching = [
            family
            for family in artifact["families"]
            if family["family_key"] == "player_game_recent_metric"
        ]

        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["dimensions"], ["player_name"])


if __name__ == "__main__":
    unittest.main()
