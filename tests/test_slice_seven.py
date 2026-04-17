# Purpose:
# Verify graph-derived BFS path resolution in grounded planning.
#
# Uses:
# - the CLI planner entrypoint
# - the direct planner-query helper for path-failure validation
#
# Produces:
# - regression coverage that discovered ontology paths now drive planning
#
# Next:
# - future deeper graph-search slices

from __future__ import annotations

import unittest

from apps.cli.main import call_haskell_planner, call_haskell_planner_for_query


class SliceSevenTests(unittest.TestCase):
    def test_player_metric_query_discovers_row_and_context_paths(self) -> None:
        planner_output = call_haskell_planner(
            "Show me players by average points over the last 10 games"
        )
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["rowObjectName"], "Player")
        self.assertEqual(resolved["rowPath"]["sourceObjectName"], "PlayerGame")
        self.assertEqual(resolved["rowPath"]["targetObjectName"], "Player")
        self.assertEqual(resolved["rowPath"]["steps"][0]["linkName"], "player_game_player")
        self.assertEqual(resolved["contextPath"]["targetObjectName"], "Team")
        self.assertEqual(resolved["contextPath"]["steps"][0]["linkName"], "player_game_team")
        self.assertNotIn("joinPath", resolved)
        self.assertNotIn("contextJoin", resolved)

    def test_team_metric_query_discovers_team_path(self) -> None:
        planner_output = call_haskell_planner(
            "Show me teams by average points over the last 10 games"
        )
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["rowObjectName"], "Team")
        self.assertEqual(resolved["rowPath"]["sourceObjectName"], "TeamGame")
        self.assertEqual(resolved["rowPath"]["targetObjectName"], "Team")
        self.assertEqual(resolved["rowPath"]["steps"][0]["linkName"], "team_game_team")
        self.assertIsNone(resolved["contextPath"])
        self.assertEqual(resolved["contextValue"]["tableRole"], "row")
        self.assertEqual(resolved["contextValue"]["columnName"], "team_abbreviation")

    def test_object_query_carries_explicit_discovered_path(self) -> None:
        planner_output = call_haskell_planner(
            "Show me players and their total points over the last 10 games"
        )
        resolved = planner_output["resolved_query"]["resolved"]

        self.assertEqual(resolved["rowPath"]["sourceObjectName"], "PlayerGame")
        self.assertEqual(resolved["rowPath"]["targetObjectName"], "Player")
        self.assertEqual(resolved["rowPath"]["steps"][0]["linkName"], "player_game_player")
        self.assertEqual(resolved["contextPath"]["targetObjectName"], "Team")
        self.assertEqual(resolved["entityId"]["tableRole"], "row")
        self.assertEqual(resolved["partitionKey"]["tableRole"], "fact")

    def test_missing_graph_path_fails_validation(self) -> None:
        impossible_query = {
            "kind": "object_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["total_points"],
                    "dimensions": ["player_name"],
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": 10,
                    "assumptions": [],
                },
                "rowObject": "Player",
            },
        }

        with self.assertRaises(RuntimeError) as context:
            call_haskell_planner_for_query(impossible_query)

        self.assertIn("No valid ontology path from 'TeamGame' to 'Player'.", str(context.exception))


if __name__ == "__main__":
    unittest.main()
