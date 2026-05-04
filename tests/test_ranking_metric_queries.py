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

import re
import unittest

import yaml

from apps.assistant.pipeline import ROOT, plan_question
from apps.cli.main import run_cli
from runtime.AnalysisRuntime.query_engine import run_sql
from tests.planner_helpers import call_plan_query_json


ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"

DERIVED_RATIO_METRIC_CASES = [
    {
        "metric": "average_three_point_attempt_rate",
        "source_attributes": ["three_pointers_attempted", "field_goals_attempted"],
        "retired_column": "three_point_attempt_rate",
    },
    {
        "metric": "average_free_throw_attempt_rate",
        "source_attributes": ["free_throws_attempted", "field_goals_attempted"],
        "retired_column": "free_throw_attempt_rate",
    },
    {
        "metric": "average_assist_to_turnover_ratio",
        "source_attributes": ["assists", "turnovers"],
        "retired_column": "assist_to_turnover_ratio",
    },
    {
        "metric": "average_field_goals_percentage",
        "source_attributes": ["field_goals_made", "field_goals_attempted"],
        "retired_column": "field_goals_percentage",
    },
    {
        "metric": "average_two_pointers_percentage",
        "source_attributes": ["two_pointers_made", "two_pointers_attempted"],
        "retired_column": "two_pointers_percentage",
    },
    {
        "metric": "average_three_pointers_percentage",
        "source_attributes": ["three_pointers_made", "three_pointers_attempted"],
        "retired_column": "three_pointers_percentage",
    },
    {
        "metric": "average_free_throws_percentage",
        "source_attributes": ["free_throws_made", "free_throws_attempted"],
        "retired_column": "free_throws_percentage",
    },
    {
        "metric": "average_effective_field_goal_percentage",
        "source_attributes": [
            "field_goals_made",
            "three_pointers_made",
            "field_goals_attempted",
        ],
        "retired_column": "effective_field_goal_percentage",
    },
    {
        "metric": "average_true_shooting_percentage",
        "source_attributes": [
            "points",
            "field_goals_attempted",
            "free_throws_attempted",
        ],
        "retired_column": "true_shooting_percentage",
    },
    {
        "metric": "total_possessions",
        "source_attributes": ["offensive_possessions", "defensive_possessions"],
        "retired_column": "possessions",
    },
    {
        "metric": "average_possessions",
        "source_attributes": ["offensive_possessions", "defensive_possessions"],
        "retired_column": "possessions",
    },
    {
        "metric": "average_pace",
        "source_attributes": [
            "offensive_possessions",
            "defensive_possessions",
            "minutes_played",
        ],
        "retired_column": "pace",
    },
    {
        "metric": "average_net_rating",
        "source_attributes": ["offensive_rating", "defensive_rating"],
        "retired_column": "net_rating",
    },
    {
        "metric": "average_steal_percentage",
        "source_attributes": ["steals", "defensive_possessions"],
        "retired_column": "steal_percentage",
    },
]

RETIRED_PLAYER_GAME_COLUMNS = {
    str(metric_case["retired_column"])
    for metric_case in DERIVED_RATIO_METRIC_CASES
}

DERIVED_TEAM_GAME_METRIC_CASES = [
    {
        "metric": "total_point_differential",
        "source_attributes": ["score", "opponent_score"],
        "retired_column": "point_differential",
    },
    {
        "metric": "average_point_differential",
        "source_attributes": ["score", "opponent_score"],
        "retired_column": "point_differential",
    },
    {
        "metric": "total_possessions",
        "source_attributes": ["offensive_possessions", "defensive_possessions"],
        "retired_column": "possessions",
    },
    {
        "metric": "average_possessions",
        "source_attributes": ["offensive_possessions", "defensive_possessions"],
        "retired_column": "possessions",
    },
    {
        "metric": "average_pace",
        "source_attributes": [
            "offensive_possessions",
            "defensive_possessions",
            "minutes_played",
        ],
        "retired_column": "pace",
    },
    {
        "metric": "average_offensive_rating",
        "source_attributes": ["score", "offensive_possessions", "defensive_possessions"],
        "retired_column": "offensive_rating",
    },
    {
        "metric": "average_defensive_rating",
        "source_attributes": [
            "opponent_score",
            "offensive_possessions",
            "defensive_possessions",
        ],
        "retired_column": "defensive_rating",
    },
    {
        "metric": "average_net_rating",
        "source_attributes": [
            "score",
            "opponent_score",
            "offensive_possessions",
            "defensive_possessions",
        ],
        "retired_column": "net_rating",
    },
    {
        "metric": "average_assist_percentage",
        "source_attributes": ["assists", "field_goals_made"],
        "retired_column": "assist_percentage",
    },
    {
        "metric": "average_assist_to_turnover_ratio",
        "source_attributes": ["assists", "turnovers"],
        "retired_column": "assist_to_turnover_ratio",
    },
    {
        "metric": "average_offensive_rebound_percentage",
        "source_attributes": ["offensive_rebounds", "opponent_defensive_rebounds"],
        "retired_column": "offensive_rebound_percentage",
    },
    {
        "metric": "average_defensive_rebound_percentage",
        "source_attributes": ["defensive_rebounds", "opponent_offensive_rebounds"],
        "retired_column": "defensive_rebound_percentage",
    },
    {
        "metric": "average_rebound_percentage",
        "source_attributes": ["total_rebounds", "opponent_total_rebounds"],
        "retired_column": "rebound_percentage",
    },
    {
        "metric": "average_steal_percentage",
        "source_attributes": ["steals", "defensive_possessions"],
        "retired_column": "steal_percentage",
    },
    {
        "metric": "average_effective_field_goal_percentage",
        "source_attributes": [
            "field_goals_made",
            "three_pointers_made",
            "field_goals_attempted",
        ],
        "retired_column": "effective_field_goal_percentage",
    },
    {
        "metric": "average_true_shooting_percentage",
        "source_attributes": ["score", "field_goals_attempted", "free_throws_attempted"],
        "retired_column": "true_shooting_percentage",
    },
    {
        "metric": "average_three_point_attempt_rate",
        "source_attributes": ["three_pointers_attempted", "field_goals_attempted"],
        "retired_column": "three_point_attempt_rate",
    },
    {
        "metric": "average_free_throw_attempt_rate",
        "source_attributes": ["free_throws_attempted", "field_goals_attempted"],
        "retired_column": "free_throw_attempt_rate",
    },
    {
        "metric": "average_field_goals_percentage",
        "source_attributes": ["field_goals_made", "field_goals_attempted"],
        "retired_column": "field_goals_percentage",
    },
    {
        "metric": "average_opponent_field_goals_percentage",
        "source_attributes": [
            "opponent_field_goals_made",
            "opponent_field_goals_attempted",
        ],
        "retired_column": "opponent_field_goals_percentage",
    },
    {
        "metric": "average_two_pointers_percentage",
        "source_attributes": ["two_pointers_made", "two_pointers_attempted"],
        "retired_column": "two_pointers_percentage",
    },
    {
        "metric": "average_opponent_two_pointers_percentage",
        "source_attributes": [
            "opponent_two_pointers_made",
            "opponent_two_pointers_attempted",
        ],
        "retired_column": "opponent_two_pointers_percentage",
    },
    {
        "metric": "average_three_pointers_percentage",
        "source_attributes": ["three_pointers_made", "three_pointers_attempted"],
        "retired_column": "three_pointers_percentage",
    },
    {
        "metric": "average_opponent_three_pointers_percentage",
        "source_attributes": [
            "opponent_three_pointers_made",
            "opponent_three_pointers_attempted",
        ],
        "retired_column": "opponent_three_pointers_percentage",
    },
    {
        "metric": "average_free_throws_percentage",
        "source_attributes": ["free_throws_made", "free_throws_attempted"],
        "retired_column": "free_throws_percentage",
    },
    {
        "metric": "average_opponent_free_throws_percentage",
        "source_attributes": [
            "opponent_free_throws_made",
            "opponent_free_throws_attempted",
        ],
        "retired_column": "opponent_free_throws_percentage",
    },
]

RETIRED_TEAM_GAME_COLUMNS = {
    str(metric_case["retired_column"])
    for metric_case in DERIVED_TEAM_GAME_METRIC_CASES
}


def metric_row_expression(expression_text: str) -> str:
    prefix = "ROUND(AVG("
    suffix = "), 1)"
    if expression_text.startswith(prefix) and expression_text.endswith(suffix):
        return expression_text[len(prefix) : -len(suffix)]
    prefix = "SUM("
    suffix = ")"
    if expression_text.startswith(prefix) and expression_text.endswith(suffix):
        return expression_text[len(prefix) : -len(suffix)]
    return expression_text


def references_retired_column(sql: str, retired_column: str) -> bool:
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_])(?:f\.)?{re.escape(retired_column)}(?![A-Za-z0-9_])"
    )
    return pattern.search(sql) is not None


def player_metric_query_payload(metric: str, limit: int | None) -> dict:
    return {
        "kind": "metric_query",
        "spec": {
            "sharedQuery": {
                "coreFactObject": "PlayerGame",
                "metrics": [metric],
                "dimensions": ["full_name"],
                "timeGrain": None,
                "filters": [{"kind": "last_n_games", "value": 10}],
                "rowPredicate": None,
                "resultPredicate": None,
                "orders": [{"kind": "desc", "metric": metric}],
                "limit": limit,
                "assumptions": [],
            },
            "entityFilters": [],
            "comparison": None,
        },
    }


def player_comparison_query_payload(metric: str) -> dict:
    return {
        "kind": "metric_query",
        "spec": {
            "sharedQuery": {
                "coreFactObject": "PlayerGame",
                "metrics": [metric],
                "dimensions": ["full_name"],
                "timeGrain": None,
                "filters": [{"kind": "last_n_games", "value": 10}],
                "rowPredicate": None,
                "resultPredicate": None,
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


def team_metric_query_payload(metric: str, limit: int | None) -> dict:
    return {
        "kind": "metric_query",
        "spec": {
            "sharedQuery": {
                "coreFactObject": "TeamGame",
                "metrics": [metric],
                "dimensions": ["team_name"],
                "timeGrain": None,
                "filters": [{"kind": "last_n_games", "value": 10}],
                "rowPredicate": None,
                "resultPredicate": None,
                "orders": [{"kind": "desc", "metric": metric}],
                "limit": limit,
                "assumptions": [],
            },
            "entityFilters": [],
            "comparison": None,
        },
    }


class RankingMetricQueryTests(unittest.TestCase):
    def test_average_points_canonical(self) -> None:
        output = run_cli("Show me players by average points over the last 10 games")
        self.assertIn("Players ranked by average points", output)
        self.assertIn("1 | Luka Dončić | LAL |", output)
        self.assertIn("Jalen Brunson | NYK |", output)

    def test_average_points_variant(self) -> None:
        output = run_cli("Show me players by avg points over the last 10 games")
        self.assertIn("Interpreted 'avg points' as average points.", output)
        self.assertIn("Average Points", output)

    def test_highest_average_scoring_variant(self) -> None:
        output = run_cli("Who has the highest average scoring over the last 10 games?")
        self.assertIn("Highest 1 players by average points", output)
        self.assertIn("average scoring", output)
        self.assertIn("average points", output)
        self.assertIn("1 | Luka Dončić | LAL |", output)

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

    def test_derived_ratio_metrics_use_raw_dependencies(self) -> None:
        for metric_case in DERIVED_RATIO_METRIC_CASES:
            metric = metric_case["metric"]
            source_attributes = metric_case["source_attributes"]
            with self.subTest(metric=metric):
                planner_output = call_plan_query_json(player_metric_query_payload(metric, 5))

                metric_formula = planner_output["resolved_query"]["resolved"]["metricFormula"]
                sql = planner_output["execution_plan"]["steps"][0]["sql"]

                self.assertEqual(metric_formula["aggregationKind"], "ratio")
                self.assertEqual(metric_formula["sourceAttributes"], source_attributes)
                self.assertIn("CASE WHEN", metric_formula["expressionText"])
                for source_attribute in source_attributes:
                    self.assertIn(f"f.{source_attribute} AS {source_attribute}", sql)
                self.assertIn("CASE WHEN", sql)
                retired_column = str(metric_case["retired_column"])
                self.assertFalse(
                    references_retired_column(sql, retired_column),
                    f"SQL still references retired player_game column {retired_column}",
                )

    def test_derived_ratio_metrics_execute_after_column_removal(self) -> None:
        for metric_case in DERIVED_RATIO_METRIC_CASES:
            metric = str(metric_case["metric"])
            with self.subTest(metric=metric):
                planner_output = call_plan_query_json(player_metric_query_payload(metric, None))
                metric_formula = planner_output["resolved_query"]["resolved"]["metricFormula"]

                actual_rows = run_sql(planner_output["execution_plan"]["steps"][0]["sql"])
                expected_rows = run_sql(
                    f"""
                    WITH recent_rows AS (
                      SELECT
                        person_id,
                        game_date,
                        {", ".join(metric_formula["sourceAttributes"])},
                        ROW_NUMBER() OVER (
                          PARTITION BY person_id
                          ORDER BY game_date DESC
                        ) AS game_rank
                      FROM player_game
                    ), ranked_players AS (
                      SELECT
                        p.full_name AS entity_name,
                        {metric_formula["expressionText"]} AS metric_value
                      FROM recent_rows r
                      JOIN player p
                        ON r.person_id = p.person_id
                      WHERE game_rank <= 10
                      GROUP BY r.person_id, p.full_name
                    )
                    SELECT entity_name, metric_value
                    FROM ranked_players
                    ORDER BY metric_value DESC, entity_name ASC
                    """
                )

                self.assertEqual(
                    [(row["entity_name"], row["metric_value"]) for row in actual_rows],
                    [(row["entity_name"], row["metric_value"]) for row in expected_rows],
                )

    def test_team_game_derived_metrics_use_raw_dependencies(self) -> None:
        for metric_case in DERIVED_TEAM_GAME_METRIC_CASES:
            metric = str(metric_case["metric"])
            retired_column = str(metric_case["retired_column"])
            source_attributes = metric_case["source_attributes"]
            with self.subTest(metric=metric):
                planner_output = call_plan_query_json(team_metric_query_payload(metric, 5))

                metric_formula = planner_output["resolved_query"]["resolved"]["metricFormula"]
                sql = planner_output["execution_plan"]["steps"][0]["sql"]

                self.assertEqual(metric_formula["aggregationKind"], "ratio")
                self.assertEqual(metric_formula["sourceAttributes"], source_attributes)
                for source_attribute in source_attributes:
                    self.assertIn(f"f.{source_attribute} AS {source_attribute}", sql)
                self.assertIn("CASE WHEN", sql)
                self.assertFalse(
                    references_retired_column(sql, retired_column),
                    f"SQL still references retired team_game column {retired_column}",
                )

    def test_team_game_derived_metrics_execute_after_column_removal(self) -> None:
        for metric_case in DERIVED_TEAM_GAME_METRIC_CASES:
            metric = str(metric_case["metric"])
            with self.subTest(metric=metric):
                planner_output = call_plan_query_json(team_metric_query_payload(metric, None))
                metric_formula = planner_output["resolved_query"]["resolved"]["metricFormula"]

                actual_rows = run_sql(planner_output["execution_plan"]["steps"][0]["sql"])
                expected_rows = run_sql(
                    f"""
                    WITH recent_rows AS (
                      SELECT
                        team_id,
                        game_date,
                        {", ".join(metric_formula["sourceAttributes"])},
                        ROW_NUMBER() OVER (
                          PARTITION BY team_id
                          ORDER BY game_date DESC
                        ) AS game_rank
                      FROM team_game
                    ), ranked_teams AS (
                      SELECT
                        t.team_name AS entity_name,
                        {metric_formula["expressionText"]} AS metric_value
                      FROM recent_rows r
                      JOIN team t
                        ON r.team_id = t.team_id
                      WHERE game_rank <= 10
                      GROUP BY r.team_id, t.team_name
                    )
                    SELECT entity_name, metric_value
                    FROM ranked_teams
                    ORDER BY metric_value DESC, entity_name ASC
                    """
                )

                self.assertEqual(
                    [(row["entity_name"], row["metric_value"]) for row in actual_rows],
                    [(row["entity_name"], row["metric_value"]) for row in expected_rows],
                )

    def test_derived_ratio_metrics_execute_after_column_removal_in_comparisons(self) -> None:
        for metric_case in DERIVED_RATIO_METRIC_CASES:
            metric = str(metric_case["metric"])
            retired_column = str(metric_case["retired_column"])
            with self.subTest(metric=metric):
                planner_output = call_plan_query_json(player_comparison_query_payload(metric))
                metric_formula = planner_output["resolved_query"]["resolved"]["metricFormula"]
                sql = planner_output["execution_plan"]["steps"][0]["sql"]

                self.assertFalse(
                    references_retired_column(sql, retired_column),
                    f"SQL still references retired player_game column {retired_column}",
                )

                actual_rows = run_sql(sql)
                expected_rows = run_sql(
                    f"""
                    WITH recent_rows AS (
                      SELECT
                        person_id,
                        game_date,
                        {", ".join(metric_formula["sourceAttributes"])},
                        ROW_NUMBER() OVER (
                          PARTITION BY person_id
                          ORDER BY game_date DESC
                        ) AS game_rank
                      FROM player_game
                      WHERE person_id IN (1628973, 1628369)
                    )
                    SELECT
                      person_id AS entity_id,
                      game_date,
                      {metric_row_expression(metric_formula["expressionText"])} AS metric_value
                    FROM recent_rows
                    WHERE game_rank <= 10
                    ORDER BY entity_id ASC, game_date DESC
                    """
                )

                self.assertEqual(
                    [
                        (row["entity_id"], row["game_date"], row["metric_value"])
                        for row in actual_rows
                    ],
                    [
                        (row["entity_id"], row["game_date"], row["metric_value"])
                        for row in expected_rows
                    ],
                )

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
        team_game_attrs = {attr["name"]: attr for attr in team_game["attributes"]}
        metrics = {metric["name"]: metric for metric in player_game["metrics"]}
        team_game_metrics = {metric["name"]: metric for metric in team_game["metrics"]}

        self.assertEqual(player_attrs["person_id"]["kind"], "primary_key")
        self.assertTrue(player_attrs["latest_team_id"]["link_key"])
        self.assertEqual(player_attrs["full_name"]["kind"], "dimension")
        self.assertEqual(player_game_attrs["game_id"]["kind"], "primary_key")
        self.assertEqual(player_game_attrs["person_id"]["kind"], "primary_key")
        self.assertEqual(player_game_attrs["points"]["kind"], "measure")
        self.assertEqual(player_game_attrs["minutes_played"]["kind"], "measure")
        self.assertTrue(RETIRED_PLAYER_GAME_COLUMNS.isdisjoint(player_game_attrs))
        self.assertTrue(
            (RETIRED_TEAM_GAME_COLUMNS - {"point_differential"}).isdisjoint(team_game_attrs)
        )
        self.assertIsNotNone(team_game_attrs["point_differential"]["derivation"])

        self.assertEqual(metrics["average_points"]["aggregation"], "avg")
        self.assertEqual(metrics["average_points"]["source_attributes"], ["points"])
        self.assertEqual(metrics["average_three_point_attempt_rate"]["aggregation"], "ratio")
        self.assertEqual(
            metrics["average_three_point_attempt_rate"]["source_attributes"],
            ["three_pointers_attempted", "field_goals_attempted"],
        )
        self.assertEqual(
            metrics["average_free_throw_attempt_rate"]["source_attributes"],
            ["free_throws_attempted", "field_goals_attempted"],
        )
        self.assertEqual(
            metrics["average_assist_to_turnover_ratio"]["source_attributes"],
            ["assists", "turnovers"],
        )
        self.assertEqual(
            metrics["average_field_goals_percentage"]["source_attributes"],
            ["field_goals_made", "field_goals_attempted"],
        )
        self.assertEqual(
            metrics["average_two_pointers_percentage"]["source_attributes"],
            ["two_pointers_made", "two_pointers_attempted"],
        )
        self.assertEqual(
            metrics["average_three_pointers_percentage"]["source_attributes"],
            ["three_pointers_made", "three_pointers_attempted"],
        )
        self.assertEqual(
            metrics["average_free_throws_percentage"]["source_attributes"],
            ["free_throws_made", "free_throws_attempted"],
        )
        self.assertEqual(
            metrics["average_effective_field_goal_percentage"]["source_attributes"],
            ["field_goals_made", "three_pointers_made", "field_goals_attempted"],
        )
        self.assertEqual(
            metrics["average_true_shooting_percentage"]["source_attributes"],
            ["points", "field_goals_attempted", "free_throws_attempted"],
        )
        self.assertEqual(
            metrics["total_possessions"]["source_attributes"],
            ["offensive_possessions", "defensive_possessions"],
        )
        self.assertEqual(
            metrics["average_possessions"]["source_attributes"],
            ["offensive_possessions", "defensive_possessions"],
        )
        self.assertEqual(
            metrics["average_pace"]["source_attributes"],
            ["offensive_possessions", "defensive_possessions", "minutes_played"],
        )
        self.assertEqual(
            metrics["average_net_rating"]["source_attributes"],
            ["offensive_rating", "defensive_rating"],
        )
        self.assertEqual(
            metrics["average_steal_percentage"]["source_attributes"],
            ["steals", "defensive_possessions"],
        )
        self.assertEqual(
            team_game_metrics["total_point_differential"]["source_attributes"],
            ["score", "opponent_score"],
        )
        self.assertEqual(
            team_game_metrics["average_pace"]["source_attributes"],
            ["offensive_possessions", "defensive_possessions", "minutes_played"],
        )
        self.assertEqual(
            team_game_metrics["average_net_rating"]["source_attributes"],
            ["score", "opponent_score", "offensive_possessions", "defensive_possessions"],
        )
        self.assertEqual(
            team_game_metrics["average_true_shooting_percentage"]["source_attributes"],
            ["score", "field_goals_attempted", "free_throws_attempted"],
        )
        self.assertEqual(
            team_game_metrics["average_field_goals_percentage"]["source_attributes"],
            ["field_goals_made", "field_goals_attempted"],
        )
        self.assertEqual(
            team_game_metrics["average_opponent_field_goals_percentage"]["source_attributes"],
            ["opponent_field_goals_made", "opponent_field_goals_attempted"],
        )
        self.assertEqual(
            team_game_metrics["average_two_pointers_percentage"]["source_attributes"],
            ["two_pointers_made", "two_pointers_attempted"],
        )
        self.assertEqual(
            team_game_metrics["average_opponent_two_pointers_percentage"]["source_attributes"],
            ["opponent_two_pointers_made", "opponent_two_pointers_attempted"],
        )
        self.assertEqual(
            team_game_metrics["average_three_pointers_percentage"]["source_attributes"],
            ["three_pointers_made", "three_pointers_attempted"],
        )
        self.assertEqual(
            team_game_metrics["average_opponent_three_pointers_percentage"]["source_attributes"],
            ["opponent_three_pointers_made", "opponent_three_pointers_attempted"],
        )
        self.assertEqual(
            team_game_metrics["average_free_throws_percentage"]["source_attributes"],
            ["free_throws_made", "free_throws_attempted"],
        )
        self.assertEqual(
            team_game_metrics["average_opponent_free_throws_percentage"]["source_attributes"],
            ["opponent_free_throws_made", "opponent_free_throws_attempted"],
        )
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
