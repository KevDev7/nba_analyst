from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml

from apps.assistant.pipeline import ROOT, plan_question
from apps.cli.main import run_cli


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"
ATTRIBUTE_INVENTORY_PATH = (
    ROOT / "pipelines" / "athena" / "metadata" / "semantic_gold_attribute_inventory.json"
)


class OntologyDrivenQueryPlanningTests(unittest.TestCase):
    def test_generated_ontology_covers_semantic_gold_inventory(self) -> None:
        ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
        inventory = json.loads(ATTRIBUTE_INVENTORY_PATH.read_text(encoding="utf-8"))

        ontology_objects = {obj["name"]: obj for obj in ontology["objects"]}
        self.assertEqual(
            set(ontology_objects),
            {
                "Player",
                "Team",
                "Game",
                "PlayerGame",
                "TeamGame",
                "PlayerSeason",
                "PlayerSeasonTeam",
                "TeamSeason",
                "Arena",
            },
        )

        for table_entry in inventory["tables"]:
            object_name = table_entry["object_name"]
            ontology_columns = {
                attribute["source_column"]: attribute
                for attribute in ontology_objects[object_name]["attributes"]
                if attribute.get("derivation") is None
            }
            inventory_columns = {column["name"]: column for column in table_entry["columns"]}
            self.assertEqual(set(ontology_columns), set(inventory_columns))
            for column_name, column in inventory_columns.items():
                ontology_attribute = ontology_columns[column_name]
                self.assertEqual(ontology_attribute["kind"], column["attribute_kind"])
                self.assertEqual(ontology_attribute["link_key"], column["link_key"])
                self.assertEqual(ontology_attribute["visibility"], column["visibility"])

    def test_generated_ontology_includes_derived_time_dimensions(self) -> None:
        ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
        objects = {obj["name"]: obj for obj in ontology["objects"]}

        for object_name in {"Game", "PlayerGame", "TeamGame"}:
            attrs = {attr["name"]: attr for attr in objects[object_name]["attributes"]}
            self.assertEqual(attrs["game_month"]["kind"], "dimension")
            self.assertEqual(attrs["game_year"]["kind"], "dimension")
            self.assertEqual(attrs["game_year_month"]["kind"], "dimension")
            self.assertEqual(attrs["game_year_month"]["source_column"], "game_date")
            self.assertIsNotNone(attrs["game_year_month"]["derivation"])

    def test_generated_ontology_promotes_public_stat_columns_to_executable_metrics(self) -> None:
        ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
        objects = {obj["name"]: obj for obj in ontology["objects"]}

        team_game_metrics = {metric["name"]: metric for metric in objects["TeamGame"]["metrics"]}
        self.assertEqual(team_game_metrics["total_points"]["source_attributes"], ["score"])
        self.assertEqual(team_game_metrics["total_point_differential"]["aggregation"], "sum")
        self.assertTrue(team_game_metrics["total_point_differential"]["executable"])
        self.assertEqual(team_game_metrics["average_offensive_rating"]["aggregation"], "avg")
        self.assertNotIn("total_offensive_rating", team_game_metrics)
        self.assertNotIn("total_assists", team_game_metrics)

        player_game_metrics = {metric["name"]: metric for metric in objects["PlayerGame"]["metrics"]}
        self.assertEqual(player_game_metrics["games_won"]["source_attributes"], ["win_loss_result"])
        self.assertEqual(player_game_metrics["games_won"]["aggregation"], "count_win")
        self.assertEqual(player_game_metrics["games_lost"]["aggregation"], "count_loss")
        self.assertEqual(player_game_metrics["games_started"]["source_attributes"], ["is_starter"])
        self.assertEqual(player_game_metrics["games_started"]["aggregation"], "count_true")

        player_season_team_metrics = {
            metric["name"]: metric for metric in objects["PlayerSeasonTeam"]["metrics"]
        }
        self.assertEqual(
            player_season_team_metrics["steals_total"]["source_attributes"],
            ["steals_total"],
        )
        self.assertEqual(player_season_team_metrics["blocks_per_game"]["aggregation"], "identity")

        team_season_metrics = {metric["name"]: metric for metric in objects["TeamSeason"]["metrics"]}
        self.assertIn("average_points", team_season_metrics)
        self.assertNotIn("assists_total", team_season_metrics)
        self.assertNotIn("rebounds_total", team_season_metrics)

    def test_team_average_points_query_is_ontology_driven(self) -> None:
        output = run_cli("Show me teams by average points over the last 10 games")
        self.assertIn("Teams ranked by average points", output)
        self.assertIn("Rank | Team | Abbrev | Games Played | Date Range | Average Points", output)
        self.assertRegex(output, r"Nuggets \| DEN \| 10 \| [0-9-]+ to [0-9-]+ \| 127\.0")

        _interpreted_query, planner_output = plan_question(
            "Show me teams by average points over the last 10 games"
        )
        self.assertEqual(planner_output["query"]["kind"], "metric_query")
        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["coreFactObject"],
            "TeamGame",
        )
        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["rowObjectName"], "Team")
        self.assertEqual(resolved["factTableName"], "team_game")
        self.assertEqual(resolved["rowTableName"], "team")
        self.assertEqual(resolved["metricFormula"]["metricKey"], "average_points")
        self.assertEqual(resolved["metricFormula"]["aggregationKind"], "avg")
        self.assertIsNone(resolved["contextPath"])
        self.assertEqual(resolved["rowPath"]["steps"][0]["linkName"], "team_game_team")

    def test_player_object_query_uses_team_context_link(self) -> None:
        _interpreted_query, planner_output = plan_question(
            "Show me players and their total points over the last 10 games"
        )
        self.assertEqual(planner_output["query"]["kind"], "object_query")
        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(resolved["rowObjectName"], "Player")
        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertEqual(resolved["rowTableName"], "player")
        self.assertEqual(resolved["rowPath"]["steps"][0]["sourceKey"], "person_id")
        self.assertEqual(resolved["rowPath"]["steps"][0]["targetKey"], "person_id")
        self.assertEqual(resolved["contextPath"]["targetObjectName"], "Team")
        self.assertEqual(resolved["contextPath"]["steps"][0]["linkName"], "player_game_team")
        self.assertEqual(resolved["contextPath"]["steps"][0]["sourceKey"], "team_id")
        self.assertEqual(resolved["contextValue"]["tableRole"], "context")
        self.assertEqual(resolved["contextValue"]["columnName"], "team_abbreviation")

if __name__ == "__main__":
    unittest.main()
