from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.assistant.pipeline import plan_question
from apps.cli.main import run_cli
from apps.assistant.semantic.interpreter import interpret_question_to_semantic_draft


def compare_draft(*entities: str) -> str:
    return json.dumps(
        {
            "status": "ok",
            "draft": {
                "task": "compare",
                "subject": "players",
                "measure": "scoring",
                "time_window": {"kind": "last_n_games", "value": 10},
                "entities": list(entities),
                "assumptions": ["Interpreted 'scoring' as points."],
            },
        }
    )


class ComparisonEntityAliasTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_family_name_alias_comparison_query(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = compare_draft("Brunson", "Tatum")
        semantic_draft, planner_output = plan_question(
            "Compare Brunson and Tatum scoring over the last 10 games"
        )

        interpreted_query = planner_output["query"]
        self.assertEqual(interpreted_query["kind"], "metric_query")
        self.assertEqual(
            interpreted_query["spec"]["sharedQuery"]["filters"],
            [{"kind": "last_n_games", "value": 10}],
        )
        self.assertEqual(interpreted_query["spec"]["entityFilters"], [])
        self.assertEqual(interpreted_query["spec"]["comparison"]["targetObject"], "Player")
        self.assertEqual(
            [entity["entityId"] for entity in interpreted_query["spec"]["comparison"]["entities"]],
            [1628973, 1628369],
        )
        self.assertEqual(
            [entity["entityName"] for entity in semantic_draft["resolved_entities"]],
            ["Jalen Brunson", "Jayson Tatum"],
        )

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(
            [entity["entityName"] for entity in resolved["comparisonEntities"]],
            ["Jalen Brunson", "Jayson Tatum"],
        )

        sql = planner_output["execution_plan"]["steps"][0]["sql"]
        self.assertIn("entity_id", sql)
        self.assertIn("IN (1628973, 1628369)", sql)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_first_name_alias_comparison_query(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = compare_draft("Ja", "Tatum")
        semantic_draft, planner_output = plan_question(
            "Compare Ja and Tatum scoring over the last 10 games"
        )

        interpreted_query = planner_output["query"]
        self.assertEqual(interpreted_query["spec"]["entityFilters"], [])
        self.assertEqual(
            [entity["entityName"] for entity in semantic_draft["resolved_entities"]],
            ["Ja Morant", "Jayson Tatum"],
        )

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_family_name_alias_comparison_output(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = compare_draft("Brunson", "Tatum")
        output = run_cli("Compare Brunson and Tatum scoring over the last 10 games")

        self.assertIn("Jalen Brunson", output)
        self.assertIn("Jayson Tatum", output)
        self.assertIn("Differential:", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_ambiguous_alias_rejected(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = compare_draft("Jalen", "Tatum")
        with self.assertRaises(RuntimeError) as context:
            run_cli("Compare Jalen and Tatum scoring over the last 10 games")

        self.assertIn("ambiguous", str(context.exception))


if __name__ == "__main__":
    unittest.main()
