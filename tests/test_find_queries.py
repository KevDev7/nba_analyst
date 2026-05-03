from __future__ import annotations

import json
from typing import Optional
import unittest
from unittest.mock import patch

import duckdb

from apps.assistant.pipeline import call_haskell_planner_for_semantic_draft
from apps.cli.main import run_cli
from apps.assistant.semantic.interpreter import interpret_question_to_semantic_draft
from runtime.AnalysisRuntime.models import ExecutionPlan
from runtime.AnalysisRuntime.runner import execute_plan
from runtime.AnswerSynthesis.package_results import package_results
from scripts.load_gold_snapshot import load_database


def lakers_games_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "find",
        "subject": "games",
        "measure": None,
        "measures": [],
        "dimensions": [],
        "filters": [
            {"field": "team", "op": "=", "value": "Lakers"},
            {"field": "points", "op": ">", "value": 120},
        ],
        "time_window": {"kind": "all", "value": None},
        "grain": None,
        "order": [],
        "limit": 5,
        "sort": None,
        "entities": ["Lakers"],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


def predicate_leaves(predicate: Optional[dict[str, object]]) -> list[dict[str, object]]:
    if not predicate:
        return []
    kind = predicate.get("kind")
    if kind == "leaf":
        return [predicate]
    if kind in {"and", "or"}:
        leaves: list[dict[str, object]] = []
        for child in predicate.get("predicates", []):
            if isinstance(child, dict):
                leaves.extend(predicate_leaves(child))
        return leaves
    if kind == "not":
        nested = predicate.get("predicate")
        if isinstance(nested, dict):
            return predicate_leaves(nested)
    return []


def assert_has_predicate_leaf(
    test: unittest.TestCase,
    predicate: Optional[dict[str, object]],
    *,
    target: str,
    attribute: str,
    operator: str,
    value: object,
    link_role: Optional[str] = None,
    label: Optional[str] = None,
) -> None:
    field = {"targetObject": target, "attribute": attribute, "location": "row"}
    if link_role is not None:
        field["linkRole"] = link_role
    if label is not None:
        field["label"] = label
    test.assertIn(
        {
            "kind": "leaf",
            "field": field,
            "operator": operator,
            "value": {"kind": "scalar", "value": value},
        },
        predicate_leaves(predicate),
    )


class FindQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_haskell_grounds_games_where_lakers_scored_over_120(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(lakers_games_draft())

        query = payload["query"]
        spec = query["spec"]
        predicate_tree = spec["findPredicateTree"]
        execution_plan = payload["execution_plan"]

        self.assertEqual(query["kind"], "find_query")
        self.assertEqual(spec["findCoreFactObject"], "TeamGame")
        self.assertEqual(spec["findTargetObject"], "Game")
        self.assertEqual(spec["findDisplayDimensions"], ["game_date", "season_year", "season_type"])
        assert_has_predicate_leaf(self, predicate_tree, target="Team", attribute="team_name", operator="equals", value="Lakers")
        assert_has_predicate_leaf(self, predicate_tree, target="TeamGame", attribute="score", operator="greater_than", value=120)
        self.assertEqual(execution_plan["query_kind"], "find_query")
        self.assertEqual(execution_plan["result_shape"], "find_rows")
        assert_has_predicate_leaf(self, execution_plan["find_predicate_tree"], target="Team", attribute="team_name", operator="equals", value="Lakers")
        assert_has_predicate_leaf(self, execution_plan["find_predicate_tree"], target="TeamGame", attribute="score", operator="greater_than", value=120)
        self.assertEqual(execution_plan["find_filters"], [])
        self.assertIn("JOIN team", execution_plan["steps"][0]["sql"])
        self.assertIn("f.score > 120", execution_plan["steps"][0]["sql"])

    def test_haskell_uses_requested_find_display_dimensions(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(dimensions=["game date", "score", "point differential"])
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findDisplayDimensions"], ["game_date", "score", "point_differential"])
        self.assertIn("r.game_date AS game_date", sql)
        self.assertIn("f.score AS score", sql)
        self.assertIn("THEN f.score - f.opponent_score ELSE NULL END AS point_differential", sql)
        self.assertIn("pt1.team_name AS team_name", sql)

        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(payload["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(payload["execution_plan"])
        runtime_result = execute_plan(execution_plan)

        self.assertTrue(runtime_result.find_rows)
        self.assertEqual(
            list(runtime_result.find_rows[0].keys()),
            ["game_date", "score", "point_differential", "team_name"],
        )

    def test_haskell_uses_ontology_alias_for_find_margin_display(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                dimensions=["game date", "opponent", "score", "margin"],
                order=[{"by": "date", "direction": "desc"}],
            )
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(
            spec["findDisplayDimensions"],
            [
                "game_date",
                {
                    "attribute": "team_name",
                    "targetObject": "Team",
                    "linkRole": "team_game_opponent_team",
                    "label": "opponent",
                },
                "score",
                "point_differential",
            ],
        )
        self.assertIn("d2.team_name AS opponent", sql)
        self.assertIn("THEN f.score - f.opponent_score ELSE NULL END AS point_differential", sql)
        self.assertIn("ORDER BY r.game_date DESC", sql)

    def test_haskell_uses_role_aware_opponent_find_display(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(dimensions=["game date", "opponent", "score"])
        )

        spec = payload["query"]["spec"]
        resolved_displays = payload["resolved_query"]["resolved"]["resolvedFindDisplays"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(
            spec["findDisplayDimensions"],
            [
                "game_date",
                {
                    "attribute": "team_name",
                    "targetObject": "Team",
                    "linkRole": "team_game_opponent_team",
                    "label": "opponent",
                },
                "score",
            ],
        )
        self.assertEqual(resolved_displays[1]["displayLabel"], "opponent")
        self.assertEqual(resolved_displays[1]["displayPath"]["steps"][0]["linkName"], "team_game_opponent_team")
        self.assertIn("d2.team_name AS opponent", sql)
        self.assertIn("ON f.opponent_team_id = d2.team_id", sql)

        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(payload["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(payload["execution_plan"])
        runtime_result = execute_plan(execution_plan)

        self.assertTrue(runtime_result.find_rows)
        self.assertEqual(
            list(runtime_result.find_rows[0].keys()),
            ["game_date", "opponent", "score", "team_name"],
        )

    def test_haskell_uses_role_aware_opponent_find_predicate(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                filters=[
                    {"field": "team name", "op": "=", "value": "Lakers"},
                    {"field": "opponent name", "op": "=", "value": "Warriors"},
                ],
                entities=["Lakers", "Warriors"],
            )
        )

        spec = payload["query"]["spec"]
        execution_plan = payload["execution_plan"]
        sql = execution_plan["steps"][0]["sql"]

        assert_has_predicate_leaf(
            self,
            spec["findPredicateTree"],
            target="Team",
            attribute="team_name",
            operator="equals",
            value="Lakers",
        )
        assert_has_predicate_leaf(
            self,
            spec["findPredicateTree"],
            target="Team",
            attribute="team_name",
            operator="equals",
            value="Warriors",
            link_role="team_game_opponent_team",
            label="opponent",
        )
        self.assertIn("ON f.team_id = pt1.team_id", sql)
        self.assertIn("ON f.opponent_team_id = pt2.team_id", sql)
        self.assertIn("pt1.team_name = 'Lakers'", sql)
        self.assertIn("pt2.team_name = 'Warriors'", sql)
        self.assertIn("opponent", json.dumps(execution_plan["find_predicate_tree"]))

    def test_haskell_uses_requested_find_order_by_score_descending(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                dimensions=["game date", "opponent", "score"],
                order=[{"by": "score", "direction": "desc"}],
            )
        )

        spec = payload["query"]["spec"]
        resolved_orders = payload["resolved_query"]["resolved"]["resolvedFindOrders"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(
            spec["findOrders"],
            [{"findOrderField": "score", "findOrderDirection": "desc"}],
        )
        self.assertEqual(resolved_orders[0]["orderLabel"], "score")
        self.assertEqual(resolved_orders[0]["orderDirection"], "desc")
        self.assertIn("ORDER BY f.score DESC", sql)

        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(payload["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(payload["execution_plan"])
        runtime_result = execute_plan(execution_plan)

        scores = [row["score"] for row in runtime_result.find_rows]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_haskell_uses_role_aware_find_order_by_opponent(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                dimensions=["game date", "score"],
                order=[{"by": "opponent", "direction": "asc"}],
            )
        )

        spec = payload["query"]["spec"]
        resolved_orders = payload["resolved_query"]["resolved"]["resolvedFindOrders"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(
            spec["findOrders"],
            [
                {
                    "findOrderField": {
                        "attribute": "team_name",
                        "targetObject": "Team",
                        "linkRole": "team_game_opponent_team",
                        "label": "opponent",
                    },
                    "findOrderDirection": "asc",
                }
            ],
        )
        self.assertEqual(resolved_orders[0]["orderLabel"], "opponent")
        self.assertEqual(resolved_orders[0]["orderPath"]["steps"][0]["linkName"], "team_game_opponent_team")
        self.assertIn("JOIN team o1", sql)
        self.assertIn("ON f.opponent_team_id = o1.team_id", sql)
        self.assertIn("ORDER BY o1.team_name ASC", sql)

    def test_haskell_applies_find_order_after_last_n_games_selection(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                dimensions=["game date", "score"],
                time_window={"kind": "last_n_games", "value": 10},
                order=[{"by": "game date", "direction": "asc"}],
                limit=None,
            )
        )

        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertIn("ROW_NUMBER() OVER (ORDER BY f.game_date DESC)", sql)
        self.assertIn("WHERE __find_row_rank <= 10", sql)
        self.assertIn("ORDER BY __find_order_1 ASC", sql)

        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(payload["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(payload["execution_plan"])
        runtime_result = execute_plan(execution_plan)

        dates = [row["game_date"] for row in runtime_result.find_rows]
        self.assertLessEqual(len(dates), 10)
        self.assertEqual(dates, sorted(dates))

    def test_haskell_uses_requested_find_display_from_fact_and_reachable_objects(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "players",
                "measure": None,
                "measures": [],
                "dimensions": ["player", "team", "minutes"],
                "filters": [{"field": "minutes", "op": ">", "value": 30}],
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [],
                "limit": 5,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findCoreFactObject"], "PlayerGame")
        self.assertEqual(spec["findTargetObject"], "Player")
        self.assertEqual(spec["findDisplayDimensions"], ["full_name", "team_name", "minutes_played"])
        self.assertIn("r.full_name AS full_name", sql)
        self.assertIn("JOIN team d2", sql)
        self.assertIn("d2.team_name AS team_name", sql)
        self.assertIn("f.minutes_played AS minutes_played", sql)

    def test_haskell_preserves_find_last_n_games_time_window(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(time_window={"kind": "last_n_games", "value": 10})
        )

        spec = payload["query"]["spec"]
        execution_plan = payload["execution_plan"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findFilters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(
            execution_plan["find_filters"],
            [{"filter_kind": "last_n_games", "filter_value": 10}],
        )
        self.assertIn("ROW_NUMBER() OVER (ORDER BY f.game_date DESC)", sql)
        self.assertIn("WHERE __find_row_rank <= 10", sql)
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            rows = conn.execute(sql).fetchall()
        self.assertLessEqual(len(rows), 10)

    def test_haskell_grounds_find_exact_season_without_duplicate_season_predicate(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                time_window={"kind": "season", "value": "2025-26"},
                filters=[
                    {"field": "team", "op": "=", "value": "Lakers"},
                    {"field": "points", "op": ">", "value": 120},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
            )
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findCoreFactObject"], "TeamGame")
        self.assertEqual(
            spec["findFilters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        season_type_leaves = [
            leaf
            for leaf in predicate_leaves(spec["findPredicateTree"])
            if leaf["field"]["attribute"] == "season_type"
        ]
        self.assertEqual(season_type_leaves, [])
        self.assertIn("f.season_year = '2025-26'", sql)
        self.assertIn("f.season_type = 'regular_season'", sql)
        self.assertNotIn("f.season_type = 'regular season'", sql)

    def test_haskell_grounds_find_exact_season_when_year_is_in_filters(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                time_window={"kind": "season", "value": None},
                filters=[
                    {"field": "team", "op": "=", "value": "Lakers"},
                    {"field": "points", "op": ">", "value": 120},
                    {"field": "season", "op": "=", "value": "2025-26"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
            )
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findCoreFactObject"], "TeamGame")
        self.assertEqual(
            spec["findFilters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(len(predicate_leaves(spec["findPredicateTree"])), 2)
        self.assertIn("f.season_year = '2025-26'", sql)
        self.assertIn("f.season_type = 'regular_season'", sql)

    def test_haskell_uses_date_backed_fact_for_find_past_year(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                subject="teams",
                filters=[{"field": "conference", "op": "=", "value": "West"}],
                time_window={"kind": "past_year", "value": None},
                entities=[],
            )
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findCoreFactObject"], "TeamGame")
        self.assertEqual(spec["findTargetObject"], "Team")
        self.assertEqual(spec["findFilters"], [{"kind": "past_year"}])
        self.assertIn("f.game_date >=", sql)

    def test_haskell_allows_time_only_find_when_scope_is_bounded(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                filters=[
                    {"field": "season", "op": "=", "value": "2025-26"},
                    {"field": "season type", "op": "=", "value": "regular season"},
                ],
                time_window={"kind": "season", "value": None},
                entities=[],
            )
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findCoreFactObject"], "Game")
        self.assertIsNone(spec["findPredicateTree"])
        self.assertEqual(
            spec["findFilters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertIn("WHERE f.season_year = '2025-26' AND f.season_type = 'regular_season'", sql)

    def test_haskell_grounds_find_team_score_field_alias(self) -> None:
        draft = lakers_games_draft(
            filters=[
                {"field": "team", "op": "=", "value": "Lakers"},
                {"field": "team score", "op": ">", "value": 120},
            ]
        )

        payload = call_haskell_planner_for_semantic_draft(draft)

        assert_has_predicate_leaf(
            self,
            payload["query"]["spec"]["findPredicateTree"],
            target="TeamGame",
            attribute="score",
            operator="greater_than",
            value=120,
        )

    def test_haskell_grounds_find_points_scored_field_alias(self) -> None:
        draft = lakers_games_draft(
            filters=[
                {"field": "team", "op": "=", "value": "Lakers"},
                {"field": "points scored", "op": ">", "value": 120},
            ]
        )

        payload = call_haskell_planner_for_semantic_draft(draft)

        assert_has_predicate_leaf(
            self,
            payload["query"]["spec"]["findPredicateTree"],
            target="TeamGame",
            attribute="score",
            operator="greater_than",
            value=120,
        )

    def test_haskell_uses_team_game_for_team_actor_points_without_lakers_corridor(self) -> None:
        draft = lakers_games_draft(
            filters=[
                {"field": "team", "op": "=", "value": "Celtics"},
                {"field": "points", "op": ">", "value": 130},
            ],
            entities=["Celtics"],
        )

        payload = call_haskell_planner_for_semantic_draft(draft)

        spec = payload["query"]["spec"]
        self.assertEqual(spec["findCoreFactObject"], "TeamGame")
        assert_has_predicate_leaf(
            self,
            spec["findPredicateTree"],
            target="TeamGame",
            attribute="score",
            operator="greater_than",
            value=130,
        )
        self.assertIn("f.score > 130", payload["execution_plan"]["steps"][0]["sql"])

    def test_haskell_uses_player_game_for_player_actor_points(self) -> None:
        draft = lakers_games_draft(
            filters=[
                {"field": "player", "op": "=", "value": "LeBron James"},
                {"field": "points", "op": ">", "value": 40},
            ],
            entities=["LeBron James"],
        )

        payload = call_haskell_planner_for_semantic_draft(draft)

        spec = payload["query"]["spec"]
        self.assertEqual(spec["findCoreFactObject"], "PlayerGame")
        assert_has_predicate_leaf(
            self,
            spec["findPredicateTree"],
            target="PlayerGame",
            attribute="points",
            operator="greater_than",
            value=40,
        )
        self.assertIn("f.points > 40", payload["execution_plan"]["steps"][0]["sql"])

    def test_runtime_packages_find_predicate_metadata_for_synthesis(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(order=[{"by": "score", "direction": "desc"}])
        )
        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(payload["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(payload["execution_plan"])

        runtime_result = execute_plan(execution_plan)
        packaged = package_results(runtime_result)

        assert_has_predicate_leaf(
            self,
            packaged.find_predicate_tree,
            target="Team",
            attribute="team_name",
            operator="equals",
            value="Lakers",
        )
        assert_has_predicate_leaf(
            self,
            packaged.find_predicate_tree,
            target="TeamGame",
            attribute="score",
            operator="greater_than",
            value=120,
        )
        self.assertEqual(len(packaged.find_orders), 1)
        self.assertEqual(packaged.find_orders[0].order_field, "score")
        self.assertEqual(packaged.find_orders[0].order_direction, "descending")

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_runs_find_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "ok", "draft": lakers_games_draft()}
        )
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            expected_date, expected_score = conn.execute(
                """
                SELECT g.game_date, tg.score
                FROM team_game tg
                JOIN game g ON tg.game_id = g.game_id
                JOIN team t ON tg.team_id = t.team_id
                WHERE t.team_name = 'Lakers' AND tg.score > 120
                ORDER BY g.game_date DESC
                LIMIT 1
                """
            ).fetchone()

        output = run_cli("Find games where the Lakers scored over 120 points")

        self.assertIn("Matching games are shown below.", output)
        self.assertIn("Game Date | Season Year | Season Type | Team Name | Score", output)
        self.assertIn(f"{expected_date} | 2025-26 | Regular Season | Lakers | {expected_score}", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_runs_find_with_requested_display_columns(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": lakers_games_draft(
                    dimensions=["game date", "score", "point differential"],
                ),
            }
        )

        output = run_cli("Find Lakers games over 120 points and show date, score, point differential")

        self.assertIn("Matching games are shown below.", output)
        self.assertIn("Game Date | Score | Point Differential | Team Name", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_runs_find_with_role_aware_opponent_display(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": lakers_games_draft(
                    dimensions=["game date", "opponent", "score"],
                ),
            }
        )

        output = run_cli("Find Lakers games over 120 points and show date, opponent, score")

        self.assertIn("Matching games are shown below.", output)
        self.assertIn("Game Date | Opponent | Score | Team Name", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_runs_find_with_requested_order(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": lakers_games_draft(
                    dimensions=["game date", "opponent", "score"],
                    order=[{"by": "score", "direction": "desc"}],
                ),
            }
        )

        output = run_cli("Find Lakers games over 120 points and show date, opponent, score, sorted by score descending")

        self.assertIn("Matching games are shown below.", output)
        self.assertIn(
            "Interpreted as: Games where team name equals Lakers and score is greater than 120 across all available data sorted by score descending.",
            output,
        )
        self.assertIn("Game Date | Opponent | Score | Team Name", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_normalizes_find_null_time_window_to_all_available_data(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "ok", "draft": lakers_games_draft(time_window=None)}
        )

        output = run_cli("Find games where the Lakers scored over 120 points")

        self.assertIn(
            "Interpreted as: Games where team name equals Lakers and score is greater than 120 across all available data.",
            output,
        )
        self.assertIn(
            "Used all available data in the local snapshot: 2020-21 through 2025-26.",
            output,
        )

    def test_haskell_grounds_team_dimension_find_without_lakers_corridor(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
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

        spec = payload["query"]["spec"]
        self.assertEqual(spec["findCoreFactObject"], "Team")
        self.assertEqual(spec["findTargetObject"], "Team")
        self.assertEqual(payload["execution_plan"]["result_shape"], "find_rows")
        assert_has_predicate_leaf(
            self,
            payload["execution_plan"]["find_predicate_tree"],
            target="Team",
            attribute="conference",
            operator="equals",
            value="west",
        )
        self.assertIn("f.conference = 'west'", payload["execution_plan"]["steps"][0]["sql"])

    def test_haskell_canonicalizes_mixed_case_conference_find_value(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "teams",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [{"field": "conference", "op": "=", "value": "eAst"}],
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

        self.assertEqual(predicate_leaves(payload["execution_plan"]["find_predicate_tree"])[0]["value"]["value"], "east")
        self.assertIn("f.conference = 'east'", payload["execution_plan"]["steps"][0]["sql"])

    def test_haskell_canonicalizes_team_name_find_value(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "teams",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [{"field": "team", "op": "=", "value": "LA Lakers"}],
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

        self.assertEqual(predicate_leaves(payload["execution_plan"]["find_predicate_tree"])[0]["value"]["value"], "Lakers")
        self.assertIn("f.team_name = 'Lakers'", payload["execution_plan"]["steps"][0]["sql"])

    def test_haskell_canonicalizes_data_backed_team_city_name_value(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "teams",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [{"field": "team", "op": "=", "value": "Salt Lake City Jazz"}],
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

        self.assertEqual(predicate_leaves(payload["execution_plan"]["find_predicate_tree"])[0]["value"]["value"], "Jazz")
        self.assertIn("f.team_name = 'Jazz'", payload["execution_plan"]["steps"][0]["sql"])

    def test_haskell_grounds_find_predicate_tree_in_and_between(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(
                filters=[],
                predicate={
                    "kind": "and",
                    "predicates": [
                        {"kind": "leaf", "field": "team", "op": "in", "value": ["Lakers", "Warriors"]},
                        {"kind": "leaf", "field": "score", "op": "between", "value": {"lower": 110, "upper": 120}},
                    ],
                },
                entities=[],
            )
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findCoreFactObject"], "TeamGame")
        self.assertEqual(spec["findPredicateTree"]["kind"], "and")
        self.assertIn("pt1.team_name IN ('Lakers', 'Warriors')", sql)
        self.assertIn("f.score BETWEEN 110 AND 120", sql)
        self.assertIn("pt1.team_name AS team_name", sql)
        self.assertIn("f.score AS score", sql)

    def test_haskell_executes_find_predicate_tree_contains(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "players",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [],
                "predicate": {"kind": "leaf", "field": "player", "op": "contains", "value": "Smith"},
                "time_window": {"kind": "all", "value": None},
                "grain": None,
                "order": [],
                "limit": 5,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertIn("f.full_name ILIKE '%Smith%'", sql)
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            rows = conn.execute(sql).fetchall()
        self.assertGreater(len(rows), 0)
        self.assertTrue(all("Smith" in row[0] for row in rows))

    def test_haskell_scopes_generic_player_name_to_player_identity(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "players",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [],
                "predicate": {"kind": "leaf", "field": "name", "op": "contains", "value": "Smith"},
                "time_window": {"kind": "all", "value": None},
                "grain": None,
                "order": [],
                "limit": 5,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        predicate_tree = payload["query"]["spec"]["findPredicateTree"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        assert_has_predicate_leaf(
            self,
            predicate_tree,
            target="Player",
            attribute="full_name",
            operator="contains",
            value="Smith",
        )
        self.assertIn("f.full_name ILIKE '%Smith%'", sql)
        self.assertNotIn("first_name ILIKE", sql)

    def test_haskell_scopes_generic_team_name_to_team_identity(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "teams",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [],
                "predicate": {"kind": "leaf", "field": "name", "op": "contains", "value": "Lake"},
                "time_window": {"kind": "all", "value": None},
                "grain": None,
                "order": [],
                "limit": 5,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        predicate_tree = payload["query"]["spec"]["findPredicateTree"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        assert_has_predicate_leaf(
            self,
            predicate_tree,
            target="Team",
            attribute="team_name",
            operator="contains",
            value="Lake",
        )
        self.assertIn("f.team_name ILIKE '%Lake%'", sql)
        self.assertNotIn("full_name ILIKE", sql)

    def test_haskell_allows_qualified_linked_identity_name_predicate(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "players",
                "measure": None,
                "measures": [],
                "dimensions": ["player", "team"],
                "filters": [],
                "predicate": {"kind": "leaf", "field": "team name", "op": "contains", "value": "Lakers"},
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [],
                "limit": 5,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        predicate_tree = payload["query"]["spec"]["findPredicateTree"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        assert_has_predicate_leaf(
            self,
            predicate_tree,
            target="Team",
            attribute="team_name",
            operator="contains",
            value="Lakers",
        )
        self.assertIn("team_name ILIKE '%Lakers%'", sql)
        self.assertIn("JOIN team", sql)

    def test_haskell_grounds_find_predicate_tree_not_and_canonicalizes_value(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "find",
                "subject": "teams",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [],
                "predicate": {
                    "kind": "not",
                    "predicate": {"kind": "leaf", "field": "conference", "op": "=", "value": "Western"},
                },
                "time_window": {"kind": "all", "value": None},
                "grain": None,
                "order": [],
                "limit": 5,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        predicate_tree = payload["execution_plan"]["find_predicate_tree"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(predicate_tree["predicate"]["value"]["value"], "west")
        self.assertIn("NOT (f.conference = 'west')", sql)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_runs_find_predicate_tree_or_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": lakers_games_draft(
                    filters=[],
                    predicate={
                        "kind": "or",
                        "predicates": [
                            {"kind": "leaf", "field": "team", "op": "=", "value": "Lakers"},
                            {"kind": "leaf", "field": "team", "op": "=", "value": "Warriors"},
                        ],
                    },
                    entities=[],
                    limit=3,
                ),
            }
        )

        output = run_cli("Find games for the Lakers or Warriors")

        self.assertIn(
            "Interpreted as: Games where (team name equals Lakers or team name equals Warriors) across all available data.",
            output,
        )
        self.assertIn("Game Date | Season Year | Season Type | Team Name", output)


if __name__ == "__main__":
    unittest.main()
