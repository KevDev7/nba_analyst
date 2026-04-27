from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import duckdb

from apps.cli.main import call_haskell_planner_for_semantic_draft, run_cli
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft
from scripts.load_gold_snapshot import load_database


def aggregate_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "aggregate",
        "subject": "teams",
        "measure": "average points",
        "measures": ["average points"],
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
    draft.update(overrides)
    return draft


class SliceFourAggregateTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_haskell_grounds_team_average_points_aggregate(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(aggregate_draft())

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        execution_plan = payload["execution_plan"]

        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["orders"], [])
        self.assertEqual(resolved["metricResultShape"], "aggregate")
        self.assertEqual(execution_plan["result_shape"], "aggregate")
        self.assertEqual(execution_plan["plan_type"], "single_sql")

    def test_haskell_grounds_non_identity_team_dimension_from_ontology(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            aggregate_draft(dimensions=["conference"])
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["conference"])
        self.assertEqual(payload["execution_plan"]["result_shape"], "aggregate")

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_cli_runs_aggregate_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": aggregate_draft()})
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            expected_name, expected_average = conn.execute(
                """
                WITH recent_rows AS (
                  SELECT
                    tg.team_id,
                    t.team_name,
                    tg.game_date,
                    tg.score,
                    ROW_NUMBER() OVER (
                      PARTITION BY tg.team_id
                      ORDER BY tg.game_date DESC
                    ) AS game_rank
                  FROM team_game tg
                  JOIN team t ON tg.team_id = t.team_id
                )
                SELECT team_name, ROUND(AVG(score), 1) AS metric_value
                FROM recent_rows
                WHERE game_rank <= 10
                GROUP BY team_id, team_name
                ORDER BY team_name ASC
                LIMIT 1
                """
            ).fetchone()

        output = run_cli("Calculate average points by team over the last 10 games")

        self.assertIn("Average points by team over the last 10 games are shown below.", output)
        self.assertIn("Team | Average Points", output)
        self.assertNotIn("Rank |", output)
        self.assertIn(f"{expected_name} | {expected_average:.1f}", output)


if __name__ == "__main__":
    unittest.main()
