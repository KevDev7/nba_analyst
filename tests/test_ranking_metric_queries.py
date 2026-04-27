# Purpose:
# Verify the gold-first governed-metric path.
#
# Uses:
# - the CLI entrypoint
# - the Haskell semantic core
# - the live ontology fixture
#
# Produces:
# - regression coverage for average_points and the architecture cutover
#
from __future__ import annotations

import unittest

import yaml

from apps.cli.main import ROOT, plan_question, run_cli


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"


class RankingMetricQueryTests(unittest.TestCase):
    def test_average_points_canonical(self) -> None:
        output = run_cli("Show me players by average points over the last 10 games")
        self.assertIn("Players ranked by average points", output)
        self.assertIn("Luka Dončić | LAL | 36.6", output)
        self.assertIn("Jalen Brunson | NYK | 24.5", output)

    def test_average_points_variant(self) -> None:
        output = run_cli("Show me players by avg points over the last 10 games")
        self.assertIn("Interpreted 'avg points' as average points.", output)
        self.assertIn("Average Points", output)

    def test_highest_average_scoring_variant(self) -> None:
        output = run_cli("Who has the highest average scoring over the last 10 games?")
        self.assertIn("Top 1 players by average points", output)
        self.assertIn("Interpreted 'average scoring' as average points.", output)
        self.assertIn("Luka Dončić | LAL | 36.6", output)

    def test_planner_resolves_governed_metric_formula(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players by average points over the last 10 games"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["metrics"],
            ["average_points"],
        )
        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["metricFormula"]["metricKey"], "average_points")
        self.assertEqual(resolved["metricFormula"]["aggregationKind"], "avg")
        self.assertEqual(resolved["metricFormula"]["expressionText"], "AVG(points)")
        self.assertEqual(resolved["filterLocation"], "fact_table")
        self.assertEqual(planner_output["execution_plan"]["metric"], "average_points")

    def test_ontology_contract_is_gold_first(self) -> None:
        ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
        objects = {obj["name"]: obj for obj in ontology["objects"]}
        player = objects["Player"]
        player_game = objects["PlayerGame"]
        team = objects["Team"]
        team_game = objects["TeamGame"]

        self.assertEqual(player["backing_table"], "player")
        self.assertEqual(player_game["backing_table"], "player_game")
        self.assertEqual(team["backing_table"], "team")
        self.assertEqual(team_game["backing_table"], "team_game")

        player_attrs = {attr["name"]: attr for attr in player["attributes"]}
        player_game_attrs = {attr["name"]: attr for attr in player_game["attributes"]}
        metrics = {metric["name"]: metric for metric in player_game["metrics"]}

        self.assertEqual(player_attrs["person_id"]["kind"], "primary_key")
        self.assertTrue(player_attrs["latest_team_id"]["link_key"])
        self.assertEqual(player_attrs["full_name"]["kind"], "dimension")
        self.assertEqual(player_game_attrs["game_id"]["kind"], "primary_key")
        self.assertEqual(player_game_attrs["person_id"]["kind"], "primary_key")
        self.assertEqual(player_game_attrs["points"]["kind"], "measure")
        self.assertEqual(player_game_attrs["minutes_played"]["kind"], "measure")

        self.assertEqual(metrics["average_points"]["aggregation"], "avg")
        self.assertEqual(metrics["average_points"]["source_attributes"], ["points"])
        self.assertTrue(metrics["average_points"]["executable"])
        self.assertFalse(metrics["games_played"]["executable"])
        self.assertFalse(metrics["points_per_36"]["executable"])

        links = {link["name"]: link for link in ontology["links"]}
        self.assertEqual(links["player_game_player"]["source_key"], "person_id")
        self.assertEqual(links["player_game_player"]["target_key"], "person_id")
        self.assertEqual(links["team_game_team"]["source_key"], "team_id")
        self.assertEqual(links["team_game_opponent_team"]["source_key"], "opponent_team_id")

if __name__ == "__main__":
    unittest.main()
