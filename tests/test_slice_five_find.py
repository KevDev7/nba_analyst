from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import duckdb

from apps.cli.main import call_haskell_planner_for_semantic_draft, run_cli
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft
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
            {"field": "score", "op": ">", "value": 120},
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


class SliceFiveFindTests(unittest.TestCase):
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
        self.assertIn("JOIN team", execution_plan["steps"][0]["sql"])
        self.assertIn("f.score > 120", execution_plan["steps"][0]["sql"])

    def test_haskell_preserves_find_last_n_games_time_window(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            lakers_games_draft(time_window={"kind": "last_n_games", "value": 10})
        )

        spec = payload["query"]["spec"]
        sql = payload["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(spec["findFilters"], [{"kind": "last_n_games", "value": 10}])
        self.assertIn("ROW_NUMBER() OVER (ORDER BY f.game_date DESC)", sql)
        self.assertIn("WHERE __find_row_rank <= 10", sql)
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            rows = conn.execute(sql).fetchall()
        self.assertLessEqual(len(rows), 10)

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
        self.assertIn("f.conference = 'Western'", payload["execution_plan"]["steps"][0]["sql"])


if __name__ == "__main__":
    unittest.main()
