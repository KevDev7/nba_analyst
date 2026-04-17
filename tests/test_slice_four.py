# Purpose:
# Verify the gold-first governed-metric cutover and stale-architecture cleanup.
#
# Uses:
# - the CLI entrypoint
# - the Haskell semantic core
# - the live ontology fixture
#
# Produces:
# - regression coverage for average_points and the architecture cutover
#
# Next:
# - future governed-metric slices

from __future__ import annotations

from pathlib import Path
import unittest

import yaml

from apps.cli.main import ROOT, call_haskell_planner, run_cli


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "minimal-nba.yaml"


class SliceFourTests(unittest.TestCase):
    def test_average_points_canonical(self) -> None:
        output = run_cli("Show me players by average points over the last 10 games")
        self.assertIn("Players ranked by average points", output)
        self.assertIn("Luka Dončić | LAL | 39.7", output)
        self.assertIn("Tyrese Haliburton | IND | 19.8", output)

    def test_average_points_variant(self) -> None:
        output = run_cli("Show me players by avg points over the last 10 games")
        self.assertIn("Interpreted 'avg points' as average points.", output)
        self.assertIn("Average Points", output)

    def test_highest_average_scoring_variant(self) -> None:
        output = run_cli("Who has the highest average scoring over the last 10 games?")
        self.assertIn("Top 1 players by average points", output)
        self.assertIn("Interpreted 'average scoring' as average points.", output)
        self.assertIn("Luka Dončić | LAL | 39.7", output)

    def test_planner_resolves_governed_metric_formula(self) -> None:
        planner_output = call_haskell_planner(
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

        self.assertEqual(player["backing_table"], "player")
        self.assertEqual(player_game["backing_table"], "player_game")

        player_attrs = {attr["name"]: attr for attr in player["attributes"]}
        player_game_attrs = {attr["name"]: attr for attr in player_game["attributes"]}
        metrics = {metric["name"]: metric for metric in player_game["metrics"]}

        self.assertEqual(player_attrs["person_id"]["kind"], "primary_key")
        self.assertEqual(player_attrs["player_name"]["kind"], "dimension")
        self.assertEqual(player_game_attrs["player_game_id"]["kind"], "primary_key")
        self.assertEqual(player_game_attrs["points"]["kind"], "measure")
        self.assertEqual(player_game_attrs["minutes_played_decimal"]["kind"], "measure")

        self.assertEqual(metrics["average_points"]["aggregation"], "avg")
        self.assertEqual(metrics["average_points"]["source_attributes"], ["points"])
        self.assertTrue(metrics["average_points"]["executable"])
        self.assertFalse(metrics["games_played"]["executable"])
        self.assertFalse(metrics["points_per_36"]["executable"])

        link = ontology["links"][0]
        self.assertEqual(link["source_key"], "person_id")
        self.assertEqual(link["target_key"], "person_id")

    def test_stale_synthetic_loader_is_removed(self) -> None:
        self.assertFalse((ROOT / "scripts" / "load_first_slice.py").exists())
        for path in [
            ROOT / "apps" / "cli" / "main.py",
            ROOT
            / "services"
            / "runtime-py"
            / "runtime"
            / "AnalysisRuntime"
            / "query_engine.py",
        ]:
            contents = path.read_text(encoding="utf-8")
            self.assertNotIn("load_first_slice", contents)


if __name__ == "__main__":
    unittest.main()
