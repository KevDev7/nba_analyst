from __future__ import annotations

import unittest

from apps.cli.main import plan_question, run_cli


class SliceThirteenTests(unittest.TestCase):
    def test_family_name_alias_comparison_query(self) -> None:
        interpreted_query, planner_output = plan_question(
            "Compare Brunson and Tatum scoring over the last 10 games"
        )

        self.assertEqual(interpreted_query["kind"], "metric_query")
        self.assertEqual(
            interpreted_query["spec"]["sharedQuery"]["filters"],
            [{"kind": "last_n_games", "value": 10}],
        )
        self.assertEqual(
            [entity["playerName"] for entity in interpreted_query["spec"]["entityFilters"]],
            ["Jalen Brunson", "Jayson Tatum"],
        )
        self.assertEqual(
            [entity["personId"] for entity in interpreted_query["spec"]["comparison"]["entities"]],
            [1628973, 1628369],
        )

        resolved = planner_output["resolved_query"]["resolved"]
        self.assertEqual(
            [entity["entityName"] for entity in resolved["comparisonEntities"]],
            ["Jalen Brunson", "Jayson Tatum"],
        )

        sql = planner_output["execution_plan"]["steps"][0]["sql"]
        self.assertIn("player_id", sql)
        self.assertIn("IN (1628973, 1628369)", sql)

    def test_first_name_alias_comparison_query(self) -> None:
        interpreted_query, _planner_output = plan_question(
            "Compare Ja and Tatum scoring over the last 10 games"
        )

        self.assertEqual(
            [entity["playerName"] for entity in interpreted_query["spec"]["entityFilters"]],
            ["Ja Morant", "Jayson Tatum"],
        )

    def test_family_name_alias_comparison_output(self) -> None:
        output = run_cli("Compare Brunson and Tatum scoring over the last 10 games")

        self.assertIn("Jalen Brunson", output)
        self.assertIn("Jayson Tatum", output)
        self.assertIn("Differential:", output)

    def test_ambiguous_alias_rejected(self) -> None:
        with self.assertRaises(RuntimeError) as context:
            run_cli("Compare Jalen and Tatum scoring over the last 10 games")

        self.assertIn("ambiguous", str(context.exception))


if __name__ == "__main__":
    unittest.main()
