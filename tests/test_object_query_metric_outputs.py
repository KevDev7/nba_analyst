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
from __future__ import annotations

import unittest

from apps.assistant.pipeline import call_haskell_planner_for_semantic_draft, plan_question
from apps.cli.main import run_cli
from tests.planner_helpers import call_plan_query_json


def object_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "object",
        "subject": "players",
        "measure": "average points",
        "measures": ["average points"],
        "dimensions": [],
        "filters": [],
        "time_window": {"kind": "last_n_games", "value": 10},
        "grain": None,
        "order": [],
        "limit": None,
        "sort": "desc",
        "entities": [],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


class ObjectQueryMetricOutputTests(unittest.TestCase):
    def test_average_points_object_query_is_accepted(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players and their average points over the last 10 games"
        )

        self.assertEqual(planner_output["query"]["kind"], "object_query")
        shared = planner_output["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
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
            shared["rowPredicate"],
            {
                "kind": "leaf",
                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                "operator": "equals",
                "value": {"kind": "scalar", "value": "Lakers"},
            },
        )

    def test_average_minutes_object_query_with_team_filter_is_accepted(self) -> None:
        planner_output = call_haskell_planner_for_semantic_draft(
            object_draft(
                measure="average minutes",
                measures=["average minutes"],
                filters=[{"field": "team", "op": "=", "value": "Lakers"}],
                entities=["Lakers"],
            )
        )

        shared = planner_output["query"]["spec"]["sharedQuery"]
        execution_plan = planner_output["execution_plan"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_minutes"])
        self.assertEqual(
            shared["rowPredicate"],
            {
                "kind": "leaf",
                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                "operator": "equals",
                "value": {"kind": "scalar", "value": "Lakers"},
            },
        )
        self.assertEqual(execution_plan["metric"], "average_minutes")
        self.assertIn("AVG(metric_source)", execution_plan["steps"][0]["sql"])

    def test_object_query_mismatched_order_is_rejected(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
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
        self.assertIn("Player | Team | Games Played | Minutes | Date Range | Average Points", output)
        self.assertRegex(output, r"Luka Dončić \| LAL \| 10 \| 38\.5 \| [0-9-]+ to [0-9-]+ \| 39\.7")

    def test_average_points_object_query_team_filter_output(self) -> None:
        output = run_cli("Show me players and their average points for the Lakers over the last 10 games")

        self.assertIn("Players ordered by average points", output)
        self.assertIn("Player | Team | Games Played | Minutes | Date Range | Average Points", output)
        self.assertRegex(output, r"Luka Dončić \| LAL \| 10 \| 38\.5 \| [0-9-]+ to [0-9-]+ \| 39\.7")
        self.assertNotIn("| GSW |", output)


if __name__ == "__main__":
    unittest.main()
