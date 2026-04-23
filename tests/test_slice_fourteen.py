# Purpose:
# Verify compositional object-query legality once object queries stop being
# hardcoded to total_points only.
#
# Uses:
# - the CLI entrypoint
# - direct Haskell query-planner invocation
#
# Produces:
# - regression coverage for average_points object queries and their legality
#
# Next:
# - future slices can broaden object-query composition further

from __future__ import annotations

import unittest

from apps.cli.main import plan_question, run_cli
from tests.planner_helpers import call_plan_query_json


class SliceFourteenTests(unittest.TestCase):
    def test_average_points_object_query_is_accepted(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players and their average points over the last 10 games"
        )

        self.assertEqual(planner_output["query"]["kind"], "object_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["player_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "average_points"}])

    def test_average_points_object_query_with_team_filter_is_accepted(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players and their average points for the Lakers over the last 10 games"
        )

        self.assertEqual(planner_output["query"]["kind"], "object_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(
            shared["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

    def test_object_query_mismatched_order_is_rejected(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["player_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": None,
                    "assumptions": [],
                },
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn("descending ordering on the selected metric", str(context.exception))

    def test_average_points_object_query_output(self) -> None:
        output = run_cli("Show me players and their average points over the last 10 games")

        self.assertIn("Players ordered by average points", output)
        self.assertIn("Player | Team | Average Points", output)
        self.assertIn("Luka Dončić | LAL | 36.6", output)

    def test_average_points_object_query_team_filter_output(self) -> None:
        output = run_cli("Show me players and their average points for the Lakers over the last 10 games")

        self.assertIn("Players ordered by average points", output)
        self.assertIn("Player | Team | Average Points", output)
        self.assertIn("Luka Dončić | LAL | 36.6", output)


if __name__ == "__main__":
    unittest.main()
