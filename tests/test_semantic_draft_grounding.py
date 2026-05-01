from __future__ import annotations

import json
import subprocess
import unittest

from apps.assistant.pipeline import ROOT


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"


def call_plan_semantic_draft(draft: dict) -> dict:
    result = subprocess.run(
        [
            "cabal",
            "run",
            "-v0",
            "--builddir=/tmp/nba-analyst-slice37a-cabal",
            "ontology-hs",
            "--",
            "plan-semantic-draft-json",
            "--ontology",
            str(ONTOLOGY_PATH),
            "--draft-json",
            json.dumps(draft),
        ],
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    payload_text = result.stdout.strip() or result.stderr.strip()
    payload = json.loads(payload_text)
    if result.returncode != 0:
        raise AssertionError(payload)
    return payload


def predicate_leaf(target: str, attribute: str, operator: str, value: object, location: str = "row") -> dict:
    return {
        "kind": "leaf",
        "field": {"targetObject": target, "attribute": attribute, "location": location},
        "operator": operator,
        "value": {"kind": "scalar", "value": value},
    }


def result_predicate_leaf(attribute: str, operator: str, value: object) -> dict:
    return predicate_leaf("", attribute, operator, value, "result")


class SemanticDraftGroundingTests(unittest.TestCase):
    def test_haskell_grounds_player_average_points_ranking_from_ontology(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "average_points"}])
        self.assertEqual(
            payload["execution_plan"]["display_metadata"],
            [
                {
                    "column_key": "games_played",
                    "label": "Games Played",
                    "column_type": "analytical_metadata",
                },
                {
                    "column_key": "minutes",
                    "label": "Minutes",
                    "column_type": "analytical_metadata",
                },
                {
                    "column_key": "date_range",
                    "label": "Date Range",
                    "column_type": "evidence",
                },
            ],
        )

    def test_haskell_grounds_object_draft_with_multiple_display_metrics(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "points",
                "measures": ["points", "rebounds", "assists"],
                "dimensions": [],
                "filters": [],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [],
                "limit": 5,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["metrics"], ["total_points", "total_rebounds", "total_assists"])
        self.assertEqual(
            plan["display_metrics"],
            [
                {"column_key": "metric_value", "label": "total_points", "metric": "total_points", "aggregation": "sum"},
                {"column_key": "metric_2", "label": "total_rebounds", "metric": "total_rebounds", "aggregation": "sum"},
                {"column_key": "metric_3", "label": "total_assists", "metric": "total_assists", "aggregation": "sum"},
            ],
        )
        self.assertIn("f.total_rebounds AS __metric_2_source", sql)
        self.assertIn("f.assists AS __metric_3_source", sql)
        self.assertIn("SUM(__metric_2_source) AS metric_2", sql)
        self.assertIn("SUM(__metric_3_source) AS metric_3", sql)
        self.assertIn("  metric_2,\n  metric_3,\n  metric_value", sql)

    def test_haskell_grounds_season_object_draft_with_team_filter_and_multiple_display_metrics(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "points",
                "measures": ["points", "assists", "rebounds"],
                "dimensions": [],
                "filters": [
                    {"field": "team", "op": "=", "value": "Lakers"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "time_window": {"kind": "season", "value": "2025-26"},
                "grain": None,
                "order": [],
                "limit": None,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["coreFactObject"], "PlayerSeasonTeam")
        self.assertEqual(shared["metrics"], ["points_total", "assists_total", "rebounds_total"])
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("Team", "team_name", "equals", "Lakers"),
        )
        self.assertEqual(
            plan["display_metrics"],
            [
                {"column_key": "metric_value", "label": "points_total", "metric": "points_total", "aggregation": "identity"},
                {"column_key": "metric_2", "label": "assists_total", "metric": "assists_total", "aggregation": "identity"},
                {"column_key": "metric_3", "label": "rebounds_total", "metric": "rebounds_total", "aggregation": "identity"},
            ],
        )
        self.assertIn("FROM player_season_team f", sql)
        self.assertIn("f.assists_total AS metric_2", sql)
        self.assertIn("f.rebounds_total AS metric_3", sql)
        self.assertIn("lf1.team_name = 'Lakers'", sql)

    def test_haskell_grounds_team_generated_metric_from_supported_team_game_data(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "teams",
                "measure": "point differential",
                "measures": ["point differential"],
                "dimensions": [],
                "filters": [],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [{"by": "point differential", "direction": "desc"}],
                "limit": 10,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["total_point_differential"])
        self.assertEqual(plan["metric"], "total_point_differential")
        self.assertEqual(plan["metric_aggregation"], "sum")
        self.assertEqual(plan["display_metrics"], [])
        self.assertIn("FROM team_game f", sql)
        self.assertIn("f.point_differential AS metric_source", sql)

    def test_haskell_grounds_team_margin_metric_from_ontology_alias(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "teams",
                "measure": "margin",
                "measures": ["margin"],
                "dimensions": [],
                "filters": [],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [{"by": "margin", "direction": "desc"}],
                "limit": 10,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["total_point_differential"])
        self.assertEqual(plan["metric"], "total_point_differential")
        self.assertIn("f.point_differential AS metric_source", sql)

    def test_haskell_grounds_monthly_team_wins_trend_from_game_outcomes(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "wins",
                "measures": ["wins"],
                "dimensions": ["team"],
                "filters": [],
                "time_window": {"kind": "between_dates", "value": "2026-01-01 to 2026-03-01"},
                "grain": "month",
                "order": [],
                "limit": None,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["wins"])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(resolved["metricFormula"]["aggregationKind"], "count_win")
        self.assertEqual(execution_plan["metric"], "wins")
        self.assertEqual(execution_plan["metric_aggregation"], "count_win")
        self.assertIn("f.win_loss_result AS metric_source", sql)
        self.assertIn("SUM(CASE WHEN metric_source = 'win' THEN 1 ELSE 0 END) AS metric_value", sql)
        self.assertIn("f.game_date >= DATE '2026-01-01'", sql)
        self.assertIn("f.game_date <= DATE '2026-03-01'", sql)

    def test_haskell_grounds_player_games_won_from_game_outcomes(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "wins",
                "measures": ["wins"],
                "dimensions": [],
                "filters": [],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [{"by": "wins", "direction": "desc"}],
                "limit": 10,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["games_won"])
        self.assertEqual(plan["metric"], "games_won")
        self.assertEqual(plan["metric_aggregation"], "count_win")
        self.assertIn("f.win_loss_result AS metric_source", sql)
        self.assertIn("SUM(CASE WHEN metric_source = 'win' THEN 1 ELSE 0 END) AS metric_value", sql)

    def test_haskell_grounds_player_starts_from_starter_flag(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "starts",
                "measures": ["starts"],
                "dimensions": [],
                "filters": [],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [{"by": "starts", "direction": "desc"}],
                "limit": 10,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["games_started"])
        self.assertEqual(plan["metric"], "games_started")
        self.assertEqual(plan["metric_aggregation"], "count_true")
        self.assertIn("f.is_starter AS metric_source", sql)
        self.assertIn("SUM(CASE WHEN metric_source THEN 1 ELSE 0 END) AS metric_value", sql)

    def test_haskell_grounds_team_multi_stats_from_team_game_metrics(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "aggregate",
                "subject": "teams",
                "measure": "points",
                "measures": ["points", "assists", "rebounds"],
                "dimensions": ["team"],
                "filters": [],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [],
                "limit": None,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["total_points", "total_assists", "total_rebounds"])
        self.assertEqual(resolved["rowObjectName"], "Team")
        self.assertEqual(resolved["factTableName"], "team_game")
        self.assertEqual(
            [metric["metricKey"] for metric in resolved["displayMetricFormulas"]],
            ["total_points", "total_assists", "total_rebounds"],
        )
        self.assertEqual(
            [metric["metric"] for metric in plan["display_metrics"]],
            ["total_points", "total_assists", "total_rebounds"],
        )
        self.assertIn("f.assists AS __metric_2_source", sql)
        self.assertIn("f.total_rebounds AS __metric_3_source", sql)
        self.assertNotIn(
            "FROM player_game",
            sql,
        )

    def test_haskell_grounds_season_object_draft_with_generated_box_score_metrics(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "points",
                "measures": ["points", "assists", "rebounds", "steals", "blocks"],
                "dimensions": [],
                "filters": [
                    {"field": "team", "op": "=", "value": "Lakers"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "time_window": {"kind": "season", "value": "2025-26"},
                "grain": None,
                "order": [],
                "limit": None,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "PlayerSeasonTeam")
        self.assertEqual(
            shared["metrics"],
            ["points_total", "assists_total", "rebounds_total", "steals_total", "blocks_total"],
        )
        self.assertEqual(
            [metric["metric"] for metric in plan["display_metrics"]],
            ["points_total", "assists_total", "rebounds_total", "steals_total", "blocks_total"],
        )
        self.assertIn("f.steals_total AS metric_4", sql)
        self.assertIn("f.blocks_total AS metric_5", sql)

    def test_haskell_prefers_team_season_surface_for_supported_team_season_metrics(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "teams",
                "measure": "average points",
                "measures": ["average points"],
                "dimensions": [],
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "time_window": {"kind": "season", "value": "2025-26"},
                "grain": None,
                "order": [{"by": "average points", "direction": "desc"}],
                "limit": 10,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamSeason")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "average_points"}])

    def test_haskell_maps_average_language_to_generated_per_game_season_metric(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average steals",
                "measures": ["average steals"],
                "dimensions": [],
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "time_window": {"kind": "season", "value": "2025-26"},
                "grain": None,
                "order": [{"by": "average steals", "direction": "desc"}],
                "limit": 10,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(shared["metrics"], ["steals_per_game"])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "steals_per_game"}])

    def test_haskell_grounds_rank_draft_with_one_sort_metric_and_display_metrics(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "points",
                "measures": ["points", "assists", "rebounds"],
                "dimensions": [],
                "filters": [],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [{"by": "points", "direction": "desc"}],
                "limit": 10,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["metrics"], ["total_points", "total_assists", "total_rebounds"])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(
            plan["display_metrics"],
            [
                {"column_key": "metric_value", "label": "total_points", "metric": "total_points", "aggregation": "sum"},
                {"column_key": "metric_2", "label": "total_assists", "metric": "total_assists", "aggregation": "sum"},
                {"column_key": "metric_3", "label": "total_rebounds", "metric": "total_rebounds", "aggregation": "sum"},
            ],
        )
        self.assertIn("ORDER BY metric_value DESC", sql)
        self.assertIn("  metric_2,\n  metric_3,\n  metric_value", sql)

    def test_haskell_grounds_rank_draft_team_filter_to_linked_filter(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "filters": [{"field": "team", "op": "=", "value": "Lakers"}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("Team", "team_name", "equals", "Lakers"),
        )
        self.assertEqual(payload["resolved_query"]["resolved"]["rowPredicateResolved"]["contents"]["rowPredicateValue"]["value"], "Lakers")
        self.assertEqual(payload["execution_plan"]["row_predicate"], predicate_leaf("Team", "team_name", "equals", "Lakers"))

    def test_haskell_grounds_season_rank_team_filter_to_team_stint_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "filters": [
                    {"field": "team", "op": "=", "value": "Lakers"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "time_window": {"kind": "season", "value": "2025-26"},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeasonTeam")
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("Team", "team_name", "equals", "Lakers"),
        )
        self.assertEqual(payload["execution_plan"]["row_predicate"], predicate_leaf("Team", "team_name", "equals", "Lakers"))

    def test_haskell_grounds_aggregate_draft_conference_filter_to_linked_filter(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "aggregate",
                "subject": "players",
                "measure": "average points",
                "dimensions": ["player"],
                "filters": [{"field": "conference", "op": "=", "value": "West"}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("Team", "conference", "equals", "West"),
        )
        self.assertEqual(payload["execution_plan"]["row_predicate"]["value"]["value"], "west")

    def test_haskell_grounds_trend_draft_conference_filter_to_linked_filter(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "players",
                "measure": "average points",
                "dimensions": ["team"],
                "filters": [{"field": "conference", "op": "=", "value": "West"}],
                "time_window": {"kind": "past_year", "value": None},
                "grain": "month",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("Team", "conference", "equals", "West"),
        )
        self.assertEqual(payload["execution_plan"]["row_predicate"]["value"]["value"], "west")

    def test_haskell_grounds_row_level_numeric_measure_filter_to_linked_filter(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "filters": [{"field": "minutes", "op": ">", "value": 30}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("PlayerGame", "minutes_played", "greater_than", 30),
        )
        self.assertEqual(resolved["rowPredicateResolved"]["contents"]["rowPredicateOperator"], "greater_than")
        self.assertEqual(resolved["rowPredicateResolved"]["contents"]["rowPredicateValue"]["value"], 30)
        self.assertIn("f.minutes_played > 30", sql)

    def test_haskell_grounds_decimal_measure_filter_from_text_value(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "teams",
                "measure": "wins",
                "filters": [
                    {"field": "win percentage", "op": "above", "value": ".600"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "time_window": {"kind": "season", "value": "2025-26"},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamSeason")
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("TeamSeason", "win_percentage", "greater_than", 0.6),
        )
        self.assertEqual(resolved["rowPredicateResolved"]["contents"]["rowPredicateValue"]["value"], 0.6)
        self.assertIn("f.win_percentage > 0.6", sql)

    def test_haskell_grounds_decimal_measure_filter_from_numeric_value(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "teams",
                "measure": "wins",
                "filters": [
                    {"field": "win percentage", "op": ">", "value": 0.6},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "time_window": {"kind": "season", "value": "2025-26"},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamSeason")
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("TeamSeason", "win_percentage", "greater_than", 0.6),
        )
        self.assertEqual(resolved["rowPredicateResolved"]["contents"]["rowPredicateValue"]["value"], 0.6)
        self.assertIn("f.win_percentage > 0.6", sql)

    def test_haskell_grounds_aggregate_numeric_measure_filter_to_linked_filter(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "aggregate",
                "subject": "players",
                "measure": "average points",
                "dimensions": ["player"],
                "filters": [{"field": "minutes", "op": ">", "value": 30}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("PlayerGame", "minutes_played", "greater_than", 30),
        )
        self.assertIn("f.minutes_played > 30", sql)

    def test_haskell_grounds_trend_numeric_measure_filter_to_linked_filter(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "average points",
                "dimensions": ["team"],
                "filters": [{"field": "score", "op": ">", "value": 120}],
                "time_window": {"kind": "past_year", "value": None},
                "grain": "month",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("TeamGame", "score", "greater_than", 120),
        )
        self.assertIn("f.score > 120", sql)

    def test_haskell_grounds_object_numeric_measure_filter_to_linked_filter(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "total points",
                "filters": [{"field": "minutes", "op": ">", "value": 30}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "limit": 5,
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("PlayerGame", "minutes_played", "greater_than", 30),
        )
        self.assertIn("f.minutes_played > 30", sql)

    def test_haskell_grounds_compare_numeric_measure_filter_to_linked_filter(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "compare",
                "subject": "players",
                "measure": "average points",
                "filters": [{"field": "minutes", "op": ">", "value": 30}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "entities": ["Jalen Brunson", "Jayson Tatum"],
                "resolved_entities": [
                    {"entityId": 1628973, "entityName": "Jalen Brunson"},
                    {"entityId": 1628369, "entityName": "Jayson Tatum"},
                ],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(payload["query"]["kind"], "metric_query")
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(
            shared["rowPredicate"],
            predicate_leaf("PlayerGame", "minutes_played", "greater_than", 30),
        )
        self.assertIn("f.minutes_played > 30", sql)

    def test_haskell_rejects_aggregate_wording_as_row_level_numeric_filter(self) -> None:
        with self.assertRaises(AssertionError) as context:
            call_plan_semantic_draft(
                {
                    "task": "rank",
                    "subject": "players",
                    "measure": "average points",
                    "filters": [{"field": "average minutes", "op": ">", "value": 30}],
                    "time_window": {"kind": "last_n_games", "value": 10},
                    "sort": "desc",
                    "assumptions": [],
                }
            )

        self.assertIn("Could not ground ranking draft", str(context.exception))

    def test_haskell_grounds_selected_metric_result_filter_for_ranking(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "total points",
                "result_filters": [{"field": "total points", "op": ">", "value": 200}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(
            shared["resultPredicate"],
            result_predicate_leaf("total_points", "greater_than", 200),
        )
        self.assertEqual(resolved["resultPredicateResolved"]["contents"]["resultPredicateKey"], "metric_value")
        self.assertEqual(plan["result_predicate"], result_predicate_leaf("total_points", "greater_than", 200))
        self.assertNotIn(
            {"column_key": "metric_value", "label": "total points", "column_type": "filter_metadata"},
            plan["display_metadata"],
        )
        self.assertIn("WHERE metric_value > 200", sql)

    def test_haskell_grounds_auxiliary_result_filter_for_ranking(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "total points",
                "result_filters": [{"field": "average minutes", "op": ">", "value": "30"}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(
            shared["resultPredicate"],
            result_predicate_leaf("average_minutes", "greater_than", 30),
        )
        self.assertEqual(resolved["resultPredicateResolved"]["contents"]["resultPredicateColumn"], "minutes_played")
        self.assertEqual(shared["resultPredicate"]["field"]["attribute"], "average_minutes")
        self.assertEqual(plan["result_predicate"]["field"]["attribute"], "average_minutes")
        self.assertIn(
            {"column_key": "result_predicate_1", "label": "average_minutes", "column_type": "filter_metadata"},
            plan["display_metadata"],
        )
        self.assertIn("f.minutes_played AS __result_predicate_1_source", sql)
        self.assertIn("ROUND(AVG(__result_predicate_1_source), 1) AS result_predicate_1", sql)
        self.assertIn("  result_predicate_1,\n  metric_value", sql)
        self.assertIn("WHERE result_predicate_1 > 30", sql)

    def test_haskell_grounds_result_predicate_tree_for_ranking(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "result_predicate": {
                    "kind": "or",
                    "predicates": [
                        {"kind": "leaf", "field": "average points", "op": "between", "value": {"lower": 20, "upper": 30}},
                        {"kind": "leaf", "field": "average minutes", "op": ">", "value": 32},
                    ],
                },
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["resultPredicate"]["kind"], "or")
        self.assertEqual(plan["result_predicate"]["kind"], "or")
        self.assertIn(
            {"column_key": "result_predicate_1", "label": "average_minutes", "column_type": "filter_metadata"},
            plan["display_metadata"],
        )
        self.assertIn("ROUND(AVG(__result_predicate_1_source), 1) AS result_predicate_1", sql)
        self.assertIn("(metric_value BETWEEN 20 AND 30 OR result_predicate_1 > 32)", sql)

    def test_haskell_grounds_identity_metric_result_filter_for_ranking(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "teams",
                "measure": "wins",
                "result_filters": [{"field": "win percentage", "op": ">", "value": 0.6}],
                "filters": [
                    {"field": "season", "op": "=", "value": "2025-26"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "time_window": {"kind": "season", "value": "2025-26"},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "TeamSeason")
        self.assertEqual(shared["metrics"], ["wins"])
        self.assertEqual(
            shared["resultPredicate"],
            result_predicate_leaf("win_percentage", "greater_than", 0.6),
        )
        self.assertEqual(resolved["resultPredicateResolved"]["contents"]["resultPredicateColumn"], "win_percentage")
        self.assertEqual(shared["resultPredicate"]["field"]["attribute"], "win_percentage")
        self.assertEqual(plan["result_predicate"]["field"]["attribute"], "win_percentage")
        self.assertIn(
            {"column_key": "result_predicate_1", "label": "win_percentage", "column_type": "filter_metadata"},
            plan["display_metadata"],
        )
        self.assertIn("f.win_percentage AS result_predicate_1", sql)
        self.assertIn("  result_predicate_1,\n  metric_value", sql)
        self.assertIn("WHERE result_predicate_1 > 0.6", sql)

    def test_haskell_grounds_auxiliary_result_filter_for_aggregate(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "aggregate",
                "subject": "players",
                "measure": "average points",
                "dimensions": ["player"],
                "result_filters": [{"field": "average minutes", "op": ">", "value": 30}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(shared["resultPredicate"]["field"]["attribute"], "average_minutes")
        self.assertIn("ROUND(AVG(__result_predicate_1_source), 1) AS result_predicate_1", sql)
        self.assertIn("WHERE result_predicate_1 > 30", sql)

    def test_haskell_grounds_selected_metric_result_filter_for_trend(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "average points",
                "dimensions": ["team"],
                "result_filters": [{"field": "average points", "op": ">", "value": 115}],
                "time_window": {"kind": "past_year", "value": None},
                "grain": "month",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]

        self.assertEqual(shared["resultPredicate"]["field"]["attribute"], "average_points")
        self.assertEqual(plan["result_predicate"]["field"]["attribute"], "average_points")
        self.assertIn("FROM aggregated_series\nWHERE metric_value > 115\nORDER BY", sql)

    def test_haskell_grounds_auxiliary_result_filter_for_object_query(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "total points",
                "result_filters": [{"field": "average minutes", "op": ">", "value": 30}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "limit": 5,
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["resultPredicate"]["field"]["attribute"], "average_minutes")
        self.assertIn("ROUND(AVG(__result_predicate_1_source), 1) AS result_predicate_1", sql)
        self.assertIn("WHERE result_predicate_1 > 30", sql)

    def test_haskell_grounds_team_points_ranking_from_ontology(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "teams",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 5,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(payload["execution_plan"]["entity_label_plural"], "Teams")
        self.assertEqual(
            payload["execution_plan"]["display_metadata"],
            [
                {
                    "column_key": "games_played",
                    "label": "Games Played",
                    "column_type": "analytical_metadata",
                },
                {
                    "column_key": "date_range",
                    "label": "Date Range",
                    "column_type": "evidence",
                }
            ],
        )

    def test_haskell_grounds_last_month_as_last_30_days(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_month", "value": 1},
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        self.assertEqual(shared["filters"], [{"kind": "last_n_days", "value": 30}])
        self.assertEqual(plan["time_filter"], "last_n_days")
        self.assertEqual(plan["time_window_days"], 30)

    def test_haskell_grounds_since_date_time_scope_for_ranking(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "time_window": {"kind": "since_date", "value": "2025-01-01"},
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]
        self.assertEqual(shared["filters"], [{"kind": "date_from", "value": "2025-01-01"}])
        self.assertEqual(plan["time_filter"], "since_date")
        self.assertEqual(plan["time_start_date"], "2025-01-01")
        self.assertIn("f.game_date >= DATE '2025-01-01'", sql)

    def test_haskell_grounds_between_dates_time_scope_for_find(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "find",
                "subject": "games",
                "measure": None,
                "filters": [{"field": "team", "op": "=", "value": "Lakers"}],
                "time_window": {"kind": "between_dates", "value": "2025-01-01 to 2025-02-01"},
                "assumptions": [],
            }
        )

        spec = payload["query"]["spec"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]
        self.assertEqual(
            spec["findFilters"],
            [
                {"kind": "date_from", "value": "2025-01-01"},
                {"kind": "date_to", "value": "2025-02-01"},
            ],
        )
        self.assertEqual(plan["time_filter"], "date_range")
        self.assertEqual(plan["time_start_date"], "2025-01-01")
        self.assertEqual(plan["time_end_date"], "2025-02-01")
        self.assertIn("f.game_date >= DATE '2025-01-01'", sql)
        self.assertIn("f.game_date <= DATE '2025-02-01'", sql)

    def test_haskell_grounds_nba_player_wording_and_arbitrary_rank_limit(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "nba players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 7,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["limit"], 7)
        self.assertEqual(payload["execution_plan"]["limit"], 7)

    def test_haskell_grounds_bottom_rank_sort_without_desc_only_gate(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 6,
                "sort": "asc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(shared["orders"], [{"kind": "asc", "metric": "total_points"}])
        self.assertEqual(payload["execution_plan"]["metric_order_direction"], "ASC")
        self.assertIn("ORDER BY metric_value ASC, entity_name ASC", sql)

    def test_haskell_grounds_season_rank_draft_through_ontology_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "time_window": {"kind": "season", "value": "2025-26"},
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(shared["metrics"], ["points_per_game"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(payload["resolved_query"]["resolved"]["factTableName"], "player_season")

    def test_haskell_grounds_season_rank_when_year_is_in_filters(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "time_window": {"kind": "season", "value": None},
                "filters": [
                    {"field": "season", "op": "=", "value": "2025-26"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertIn("WITH season_ranked_entities AS", sql)
        self.assertNotIn("game_rank <=", sql)

    def test_haskell_grounds_recent_rank_with_season_constraint_on_game_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "time_window": {"kind": "last_n_games", "value": 8},
                "filters": [
                    {"field": "season", "op": "=", "value": "2024-25"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "last_n_games", "value": 8},
                {"kind": "exact_season", "value": "2024-25"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(resolved["windowGames"], 8)
        self.assertEqual(resolved["seasonLabel"], "2024-25")
        self.assertIn("f.season_year = '2024-25'", sql)
        self.assertIn("f.season_type = 'regular_season'", sql)
        self.assertIn("WHERE game_rank <= 8", sql)

    def test_haskell_grounds_object_draft_to_object_query(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "total points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(payload["query"]["spec"]["rowObject"], "Player")
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(payload["execution_plan"]["result_shape"], "object_rows")

    def test_haskell_grounds_scoring_totals_object_draft_to_total_points(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "scoring totals",
                "time_window": {"kind": "last_n_games", "value": 10},
                "sort": "desc",
                "assumptions": ["Interpreted 'scoring' as total points."],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(payload["execution_plan"]["result_shape"], "object_rows")

    def test_haskell_grounds_season_object_draft_to_object_query(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "total points",
                "time_window": {"kind": "season", "value": "2025-26"},
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(shared["metrics"], ["points_total"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(payload["execution_plan"]["result_shape"], "object_rows")

    def test_haskell_grounds_season_object_when_year_is_in_filters(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "total points",
                "time_window": {"kind": "season", "value": None},
                "filters": [
                    {"field": "season", "op": "=", "value": "2025-26"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertIn("WITH season_entity_values AS", sql)
        self.assertNotIn("game_rank <=", sql)

    def test_haskell_grounds_recent_object_with_season_constraint_on_game_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "object",
                "subject": "players",
                "measure": "average points",
                "time_window": {"kind": "last_n_games", "value": 8},
                "filters": [
                    {"field": "season", "op": "=", "value": "2024-25"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(payload["query"]["kind"], "object_query")
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(resolved["windowGames"], 8)
        self.assertEqual(resolved["seasonLabel"], "2024-25")
        self.assertIn("f.season_year = '2024-25'", sql)
        self.assertIn("WHERE game_rank <= 8", sql)

    def test_haskell_grounds_monthly_team_trend_from_ontology(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "average points",
                "dimensions": ["team"],
                "time_window": {"kind": "past_year", "value": None},
                "grain": "month",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(shared["filters"], [{"kind": "past_year"}])
        self.assertEqual(payload["execution_plan"]["result_shape"], "time_series")

    def test_haskell_grounds_weekly_team_trend_from_same_date_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "average points",
                "dimensions": ["team"],
                "time_window": {"kind": "past_year", "value": None},
                "grain": "week",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["timeGrain"], "week")
        self.assertIn("DATE_TRUNC('week'", resolved["timeBucketExpression"])
        self.assertEqual(payload["execution_plan"]["time_grain"], "week")

    def test_haskell_grounds_season_team_trend_through_season_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "wins",
                "dimensions": ["team"],
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "time_window": {"kind": "all", "value": None},
                "grain": "season",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamSeason")
        self.assertEqual(shared["metrics"], ["wins"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["timeGrain"], "season")
        self.assertEqual(shared["filters"], [{"kind": "season_type", "value": "regular_season"}])
        self.assertEqual(payload["resolved_query"]["resolved"]["factTableName"], "team_season")

    def test_haskell_grounds_monthly_team_trend_inside_exact_season(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "average points",
                "dimensions": ["team"],
                "filters": [
                    {"field": "season", "op": "=", "value": "2025-26"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "time_window": {"kind": "season", "value": None},
                "grain": "month",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        plan = payload["execution_plan"]
        sql = plan["steps"][0]["sql"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertIsNone(shared["rowPredicate"])
        self.assertEqual(resolved["trendSeasonLabel"], "2025-26")
        self.assertEqual(resolved["trendSeasonType"], "regular_season")
        self.assertEqual(plan["season_label"], "2025-26")
        self.assertEqual(plan["season_type"], "regular_season")
        self.assertIn("f.season_year = '2025-26'", sql)
        self.assertIn("f.season_type = 'regular_season'", sql)

    def test_haskell_grounds_monthly_team_trend_when_exact_season_lives_in_filters(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "average points",
                "dimensions": ["team"],
                "filters": [
                    {"field": "year", "op": "=", "value": "2526"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "time_window": {"kind": "month", "value": None},
                "grain": "month",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )

    def test_haskell_grounds_player_comparison_from_resolved_entities(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "compare",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "entities": ["Brunson", "Tatum"],
                "resolved_entities": [
                    {"entityId": 1628973, "entityName": "Jalen Brunson"},
                    {"entityId": 1628369, "entityName": "Jayson Tatum"},
                ],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        comparison = payload["query"]["spec"]["comparison"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(comparison["targetObject"], "Player")
        self.assertEqual(payload["execution_plan"]["result_shape"], "comparison")
        self.assertEqual(payload["execution_plan"]["plan_type"], "multi_step")

    def test_haskell_rejects_result_filters_for_comparison_drafts(self) -> None:
        with self.assertRaises(AssertionError) as context:
            call_plan_semantic_draft(
                {
                    "task": "compare",
                    "subject": "players",
                    "measure": "points",
                    "result_filters": [{"field": "average points", "op": ">", "value": 20}],
                    "time_window": {"kind": "last_n_games", "value": 10},
                    "entities": ["Brunson", "Tatum"],
                    "resolved_entities": [
                        {"entityId": 1628973, "entityName": "Jalen Brunson"},
                        {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    ],
                    "assumptions": [],
                }
            )

        self.assertIn("Comparison result filters are not supported", str(context.exception))

    def test_haskell_grounds_recent_comparison_with_season_constraint(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "compare",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 8},
                "filters": [
                    {"field": "season", "op": "=", "value": "2024-25"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                "entities": ["Brunson", "Tatum"],
                "resolved_entities": [
                    {"entityId": 1628973, "entityName": "Jalen Brunson"},
                    {"entityId": 1628369, "entityName": "Jayson Tatum"},
                ],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(resolved["windowGames"], 8)
        self.assertEqual(resolved["seasonLabel"], "2024-25")
        self.assertIn("f.season_year = '2024-25'", sql)
        self.assertIn("f.season_type = 'regular_season'", sql)
        self.assertIn("WHERE game_rank <= 8", sql)

    def test_haskell_grounds_season_player_comparison_from_semantic_draft(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "compare",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "season", "value": "2025-26"},
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "entities": ["Jalen Brunson", "Jayson Tatum"],
                "resolved_entities": [
                    {"entityId": 1628973, "entityName": "Jalen Brunson"},
                    {"entityId": 1628369, "entityName": "Jayson Tatum"},
                ],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(shared["metrics"], ["points_total"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(resolved["windowGames"], 0)
        self.assertEqual(execution_plan["season_label"], "2025-26")
        self.assertIn("WITH season_rows AS", sql)
        self.assertIn("f.points_total AS metric_value", sql)
        self.assertNotIn("game_rank <=", sql)

    def test_haskell_grounds_time_bucketed_season_comparison_to_game_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "compare",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "season", "value": "2025-26"},
                "grain": "month",
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "entities": ["Jalen Brunson", "Jayson Tatum"],
                "resolved_entities": [
                    {"entityId": 1628973, "entityName": "Jalen Brunson"},
                    {"entityId": 1628369, "entityName": "Jayson Tatum"},
                ],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(resolved["factTableName"], "player_game")
        self.assertEqual(resolved["metricTimeGrain"], "month")
        self.assertEqual(execution_plan["time_grain"], "month")
        self.assertIn("WITH recent_rows AS", sql)
        self.assertIn("STRFTIME(f.game_date, '%Y-%m') AS time_bucket", sql)
        self.assertIn("f.season_year = '2025-26'", sql)
        self.assertIn("f.season_type = 'regular_season'", sql)
        self.assertNotIn("WITH season_rows AS", sql)

    def test_haskell_grounds_multi_entity_comparison_without_two_entity_gate(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "compare",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "entities": ["Brunson", "Tatum", "Haliburton"],
                "resolved_entities": [
                    {"entityId": 1628973, "entityName": "Jalen Brunson"},
                    {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    {"entityId": 1630169, "entityName": "Tyrese Haliburton"},
                ],
                "assumptions": [],
            }
        )

        comparison = payload["query"]["spec"]["comparison"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(len(comparison["entities"]), 3)
        self.assertIn("1628973", sql)
        self.assertIn("1630169", sql)

    def test_haskell_grounds_find_family_from_semantic_draft(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "find",
                "subject": "teams",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [{"field": "conference", "op": "=", "value": "Western"}],
                "time_window": {"kind": "all", "value": None},
                "grain": None,
                "order": [],
                "limit": 3,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        self.assertEqual(payload["query"]["kind"], "find_query")
        self.assertEqual(payload["query"]["spec"]["findCoreFactObject"], "Team")
        self.assertEqual(payload["execution_plan"]["result_shape"], "find_rows")

    def test_haskell_grounds_find_players_with_fact_measure_predicate(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "find",
                "subject": "players",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [{"field": "minutes", "op": ">", "value": 30}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [],
                "limit": None,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        query = payload["query"]["spec"]
        resolved = payload["resolved_query"]["resolved"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(payload["query"]["kind"], "find_query")
        self.assertEqual(query["findCoreFactObject"], "PlayerGame")
        self.assertEqual(query["findTargetObject"], "Player")
        self.assertEqual(
            query["findPredicateTree"],
            predicate_leaf("PlayerGame", "minutes_played", "greater_than", 30),
        )
        self.assertEqual(resolved["resolvedFindPredicateTree"]["contents"]["treePredicateColumn"], "minutes_played")
        self.assertIn("f.minutes_played > 30", sql)


if __name__ == "__main__":
    unittest.main()
