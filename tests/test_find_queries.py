from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import duckdb

from apps.cli.main import call_haskell_planner_for_semantic_draft, run_cli
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft
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


class FindQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_haskell_grounds_games_where_lakers_scored_over_120(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(lakers_games_draft())

        query = payload["query"]
        spec = query["spec"]
        predicates = spec["findPredicates"]
        execution_plan = payload["execution_plan"]

        self.assertEqual(query["kind"], "find_query")
        self.assertEqual(spec["findCoreFactObject"], "TeamGame")
        self.assertEqual(spec["findTargetObject"], "Game")
        self.assertEqual(spec["findDisplayDimensions"], ["game_date", "season_year", "season_type"])
        self.assertIn(
            {
                "predicateTargetObject": "Team",
                "predicateAttribute": "team_name",
                "predicateOperator": "=",
                "predicateFilterValue": "Lakers",
            },
            predicates,
        )
        self.assertIn(
            {
                "predicateTargetObject": "TeamGame",
                "predicateAttribute": "score",
                "predicateOperator": ">",
                "predicateFilterValue": 120,
            },
            predicates,
        )
        self.assertEqual(execution_plan["query_kind"], "find_query")
        self.assertEqual(execution_plan["result_shape"], "find_rows")
        self.assertEqual(
            execution_plan["find_predicates"],
            [
                {
                    "target_object": "Team",
                    "attribute": "team_name",
                    "operator": "=",
                    "value": "Lakers",
                },
                {
                    "target_object": "TeamGame",
                    "attribute": "score",
                    "operator": ">",
                    "value": 120,
                },
            ],
        )
        self.assertEqual(execution_plan["find_filters"], [])
        self.assertIn("JOIN team", execution_plan["steps"][0]["sql"])
        self.assertIn("f.score > 120", execution_plan["steps"][0]["sql"])

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

    def test_haskell_grounds_find_team_score_field_alias(self) -> None:
        draft = lakers_games_draft(
            filters=[
                {"field": "team", "op": "=", "value": "Lakers"},
                {"field": "team score", "op": ">", "value": 120},
            ]
        )

        payload = call_haskell_planner_for_semantic_draft(draft)

        self.assertIn(
            {
                "predicateTargetObject": "TeamGame",
                "predicateAttribute": "score",
                "predicateOperator": ">",
                "predicateFilterValue": 120,
            },
            payload["query"]["spec"]["findPredicates"],
        )

    def test_haskell_grounds_find_points_scored_field_alias(self) -> None:
        draft = lakers_games_draft(
            filters=[
                {"field": "team", "op": "=", "value": "Lakers"},
                {"field": "points scored", "op": ">", "value": 120},
            ]
        )

        payload = call_haskell_planner_for_semantic_draft(draft)

        self.assertIn(
            {
                "predicateTargetObject": "TeamGame",
                "predicateAttribute": "score",
                "predicateOperator": ">",
                "predicateFilterValue": 120,
            },
            payload["query"]["spec"]["findPredicates"],
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
        self.assertIn(
            {
                "predicateTargetObject": "TeamGame",
                "predicateAttribute": "score",
                "predicateOperator": ">",
                "predicateFilterValue": 130,
            },
            spec["findPredicates"],
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
        self.assertIn(
            {
                "predicateTargetObject": "PlayerGame",
                "predicateAttribute": "points",
                "predicateOperator": ">",
                "predicateFilterValue": 40,
            },
            spec["findPredicates"],
        )
        self.assertIn("f.points > 40", payload["execution_plan"]["steps"][0]["sql"])

    def test_runtime_packages_find_predicate_metadata_for_synthesis(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(lakers_games_draft())
        if hasattr(ExecutionPlan, "model_validate"):
            execution_plan = ExecutionPlan.model_validate(payload["execution_plan"])
        else:
            execution_plan = ExecutionPlan.parse_obj(payload["execution_plan"])

        runtime_result = execute_plan(execution_plan)
        packaged = package_results(runtime_result)

        serialized_predicates = [
            predicate.model_dump() if hasattr(predicate, "model_dump") else predicate.dict()
            for predicate in packaged.find_predicates
        ]
        self.assertEqual(
            serialized_predicates,
            [
                {
                    "target_object": "Team",
                    "attribute": "team_name",
                    "operator": "=",
                    "value": "Lakers",
                },
                {
                    "target_object": "TeamGame",
                    "attribute": "score",
                    "operator": ">",
                    "value": 120,
                },
            ],
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
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

    @patch("apps.cli.semantic_interpreter._call_gemini")
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
        self.assertEqual(
            payload["execution_plan"]["find_predicates"],
            [
                {
                    "target_object": "Team",
                    "attribute": "conference",
                    "operator": "=",
                    "value": "west",
                }
            ],
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

        self.assertEqual(payload["execution_plan"]["find_predicates"][0]["value"], "east")
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

        self.assertEqual(payload["execution_plan"]["find_predicates"][0]["value"], "Lakers")
        self.assertIn("f.team_name = 'Lakers'", payload["execution_plan"]["steps"][0]["sql"])


if __name__ == "__main__":
    unittest.main()
