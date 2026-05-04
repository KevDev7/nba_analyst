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

    def test_generated_ontology_includes_metric_ranking_polarity(self) -> None:
        ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
        objects = {obj["name"]: obj for obj in ontology["objects"]}

        allowed_polarities = {"higher_is_better", "lower_is_better", "neutral"}
        for ontology_object in objects.values():
            for metric in ontology_object["metrics"]:
                self.assertIn("ranking_polarity", metric)
                self.assertIn(metric["ranking_polarity"], allowed_polarities)

        team_game_metrics = {metric["name"]: metric for metric in objects["TeamGame"]["metrics"]}
        player_game_metrics = {metric["name"]: metric for metric in objects["PlayerGame"]["metrics"]}
        team_season_metrics = {metric["name"]: metric for metric in objects["TeamSeason"]["metrics"]}

        self.assertEqual(team_game_metrics["average_defensive_rating"]["ranking_polarity"], "lower_is_better")
        self.assertEqual(team_game_metrics["average_net_rating"]["ranking_polarity"], "higher_is_better")
        self.assertEqual(
            team_game_metrics["average_opponent_field_goals_percentage"]["ranking_polarity"],
            "lower_is_better",
        )
        self.assertEqual(team_game_metrics["average_opponent_turnovers"]["ranking_polarity"], "higher_is_better")
        self.assertEqual(team_game_metrics["average_pace"]["ranking_polarity"], "neutral")
        self.assertEqual(team_game_metrics["total_field_goals_attempted"]["ranking_polarity"], "neutral")
        self.assertEqual(player_game_metrics["total_turnovers"]["ranking_polarity"], "lower_is_better")
        self.assertEqual(player_game_metrics["total_fouls_drawn"]["ranking_polarity"], "higher_is_better")
        self.assertEqual(team_season_metrics["defensive_rating"]["ranking_polarity"], "lower_is_better")
        self.assertEqual(team_season_metrics["pace"]["ranking_polarity"], "neutral")

    def test_generated_ontology_promotes_public_stat_columns_to_executable_metrics(self) -> None:
        ontology = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
        objects = {obj["name"]: obj for obj in ontology["objects"]}

        team_game_metrics = {metric["name"]: metric for metric in objects["TeamGame"]["metrics"]}
        team_game_attributes = {attribute["name"]: attribute for attribute in objects["TeamGame"]["attributes"]}
        self.assertEqual(team_game_metrics["total_points"]["source_attributes"], ["score"])
        self.assertEqual(team_game_metrics["total_point_differential"]["aggregation"], "ratio")
        self.assertTrue(team_game_metrics["total_point_differential"]["executable"])
        self.assertIsNotNone(team_game_attributes["point_differential"]["derivation"])
        self.assertIn("margin", team_game_metrics["total_point_differential"]["aliases"])
        self.assertIn("average margin", team_game_metrics["average_point_differential"]["aliases"])
        self.assertEqual(team_game_metrics["average_offensive_rating"]["aggregation"], "ratio")
        self.assertIn("ortg", team_game_metrics["average_offensive_rating"]["aliases"])
        self.assertEqual(team_game_metrics["total_assists"]["source_attributes"], ["assists"])
        self.assertIn("ast", team_game_metrics["total_assists"]["aliases"])
        self.assertIn("asts", team_game_metrics["total_assists"]["aliases"])
        self.assertEqual(team_game_metrics["average_assists"]["aggregation"], "avg")
        self.assertEqual(team_game_metrics["total_rebounds"]["source_attributes"], ["total_rebounds"])
        self.assertIn("boards", team_game_metrics["total_rebounds"]["aliases"])
        self.assertIn("rebs", team_game_metrics["total_rebounds"]["aliases"])
        self.assertEqual(team_game_metrics["average_rebounds"]["source_attributes"], ["total_rebounds"])
        self.assertEqual(team_game_metrics["total_steals"]["source_attributes"], ["steals"])
        self.assertIn("stl", team_game_metrics["total_steals"]["aliases"])
        self.assertIn("stls", team_game_metrics["total_steals"]["aliases"])
        self.assertEqual(team_game_metrics["total_blocks"]["source_attributes"], ["blocks"])
        self.assertIn("blk", team_game_metrics["total_blocks"]["aliases"])
        self.assertIn("blks", team_game_metrics["total_blocks"]["aliases"])
        self.assertEqual(
            team_game_metrics["total_field_goals_made"]["source_attributes"],
            ["field_goals_made"],
        )
        self.assertIn("fgm", team_game_metrics["total_field_goals_made"]["aliases"])
        self.assertNotIn("total_offensive_rating", team_game_metrics)
        self.assertEqual(
            team_game_metrics["average_pace"]["source_attributes"],
            ["offensive_possessions", "defensive_possessions", "minutes_played"],
        )
        self.assertEqual(
            team_game_metrics["average_assist_to_turnover_ratio"]["source_attributes"],
            ["assists", "turnovers"],
        )
        self.assertIn("ast/to", team_game_metrics["average_assist_to_turnover_ratio"]["aliases"])
        self.assertEqual(
            team_game_metrics["average_true_shooting_percentage"]["source_attributes"],
            ["score", "field_goals_attempted", "free_throws_attempted"],
        )
        self.assertIn("ts%", team_game_metrics["average_true_shooting_percentage"]["aliases"])
        self.assertEqual(
            team_game_metrics["average_field_goals_percentage"]["source_attributes"],
            ["field_goals_made", "field_goals_attempted"],
        )
        self.assertIn("fg%", team_game_metrics["average_field_goals_percentage"]["aliases"])
        self.assertEqual(
            team_game_metrics["average_opponent_field_goals_percentage"]["source_attributes"],
            ["opponent_field_goals_made", "opponent_field_goals_attempted"],
        )
        self.assertIn("opp points", team_game_metrics["total_opponent_points"]["aliases"])
        self.assertIn("opponents pts", team_game_metrics["total_opponent_points"]["aliases"])
        self.assertIn("points allowed", team_game_metrics["total_opponent_points"]["aliases"])
        self.assertIn("fg% allowed", team_game_metrics["average_opponent_field_goals_percentage"]["aliases"])
        self.assertIn("allowed 3pa", team_game_metrics["total_opponent_three_pointers_attempted"]["aliases"])
        self.assertIn("points off to", team_game_metrics["total_points_off_turnovers"]["aliases"])
        self.assertIn("plusminus", team_game_metrics["total_point_differential"]["aliases"])
        self.assertIn("blka", team_game_metrics["total_opponent_blocks"]["aliases"])
        self.assertIn("pfd", team_game_metrics["total_fouls_drawn"]["aliases"])
        self.assertIn("w", team_game_metrics["wins"]["aliases"])
        self.assertIn("l", team_game_metrics["losses"]["aliases"])

        player_game_metrics = {metric["name"]: metric for metric in objects["PlayerGame"]["metrics"]}
        self.assertEqual(player_game_metrics["games_won"]["source_attributes"], ["win_loss_result"])
        self.assertEqual(player_game_metrics["games_won"]["aggregation"], "count_win")
        self.assertEqual(player_game_metrics["games_lost"]["aggregation"], "count_loss")
        self.assertEqual(player_game_metrics["games_started"]["source_attributes"], ["is_starter"])
        self.assertEqual(player_game_metrics["games_started"]["aggregation"], "count_true")
        self.assertIn("pf", player_game_metrics["total_personal_fouls_committed"]["aliases"])
        self.assertIn("pfs", player_game_metrics["total_personal_fouls_committed"]["aliases"])
        self.assertIn("techs", player_game_metrics["total_technical_fouls_committed"]["aliases"])
        self.assertIn("drawn fouls", player_game_metrics["total_fouls_drawn"]["aliases"])
        self.assertIn("pfd", player_game_metrics["total_fouls_drawn"]["aliases"])
        self.assertIn("blka", player_game_metrics["total_opponent_blocks"]["aliases"])
        self.assertIn("fb points", player_game_metrics["total_fast_break_points"]["aliases"])
        self.assertIn("pitp", player_game_metrics["total_points_in_paint"]["aliases"])
        self.assertIn("2nd chance points", player_game_metrics["total_second_chance_points"]["aliases"])

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
        self.assertIn("assists_total", team_season_metrics)
        self.assertIn("assists_per_game", team_season_metrics)
        self.assertIn("rebounds_total", team_season_metrics)
        self.assertIn("rebounds_per_game", team_season_metrics)
        self.assertIn("steals_total", team_season_metrics)
        self.assertIn("blocks_total", team_season_metrics)
        self.assertIn("true_shooting_percentage", team_season_metrics)
        self.assertIn("ppg", team_season_metrics["points_per_game"]["aliases"])
        self.assertIn("wpct", team_season_metrics["win_percentage"]["aliases"])
        self.assertIn("efg%", team_season_metrics["effective_field_goal_percentage"]["aliases"])
        self.assertIn("3par", team_season_metrics["three_point_attempt_rate"]["aliases"])
        self.assertIn("gp", team_season_metrics["games_played"]["aliases"])
        self.assertIn("fg3%", team_season_metrics["three_pointers_percentage"]["aliases"])

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
