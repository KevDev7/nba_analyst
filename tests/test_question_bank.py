# Purpose:
# Keep a persistent bank of supported and intentionally unsupported questions
# so architecture changes do not erase previously tested behavior.
#
# Uses:
# - the eval question bank JSON
# - unittest validation over retained question coverage
#
# Produces:
# - one place to remember canonical questions across slices
#
from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUESTION_BANK_PATH = ROOT / "evals" / "question_bank.json"


RETAINED_QUESTIONS = {
    "Show me the top 10 players by points over the last 10 games",
    "Who are the top 10 scorers over the last 10 games?",
    "Show me the top 10 players by pts over the last 10 games",
    "Show me the top 5 players by points over the last 10 games",
    "What is the trend in points over the last month?",
    "Compare Brunson and Haliburton scoring over the last 10 games",
    "Compare Jalen Brunson and Tyrese Haliburton scoring over the last 10 games",
    "Compare Brunson and Haliburton pts over the last 10 games",
    "Compare Brunson and Tatum scoring over the last 10 games",
    "Compare Ja and Tatum scoring over the last 10 games",
    "Compare Jalen and Tatum scoring over the last 10 games",
    "Compare Brunson, Haliburton, and Tatum scoring over the last 10 games",
    "Show me all information about Brunson",
    "Show me players and their total points over the last 10 games",
    "Show me players with their scoring totals over the last 10 games",
    "Show me players and their average points over the last 10 games",
    "Show me players and their average points for the Lakers over the last 10 games",
    "Show me players and their assists over the last 10 games",
    "Show me games and their players",
    "Show me players by average points over the last 10 games",
    "Show me players by avg points over the last 10 games",
    "Who has the highest average scoring over the last 10 games?",
    "Show me teams by average points over the last 10 games",
    "What are the monthly average points over the past year?",
    "What are the monthly average points by team over the past year?",
    "Show me players by average points in the 2025-26 regular season",
    "Show me teams by wins in the 2025-26 regular season",
    "Show me players and their total points in the 2025-26 regular season",
    "Show me players by average points for the Lakers over the last 10 games",
    "Show me players and their total points for the Knicks over the last 10 games",
    "Show me the top 5 players and their total points for the Knicks over the last 10 games",
    "Show me players by average points for the Lakers in the 2025-26 regular season",
}


class QuestionBankTests(unittest.TestCase):
    def test_question_bank_exists_and_is_versioned(self) -> None:
        payload = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertIn("cases", payload)
        self.assertGreater(len(payload["cases"]), 0)

    def test_question_bank_retains_supported_and_unsupported_slice_questions(self) -> None:
        payload = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
        questions = {case["question"] for case in payload["cases"]}
        self.assertEqual(questions, RETAINED_QUESTIONS)

    def test_question_bank_ids_and_questions_are_unique(self) -> None:
        payload = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
        ids = [case["id"] for case in payload["cases"]]
        questions = [case["question"] for case in payload["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(questions), len(set(questions)))

    def test_supported_cases_have_query_shape_metadata(self) -> None:
        payload = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
        for case in payload["cases"]:
            self.assertIn(case["status"], {"supported", "unsupported"})
            self.assertIn("query_kind", case)
            if case["status"] == "supported":
                self.assertIn("core_fact_object", case)
                self.assertIn("capability", case)


if __name__ == "__main__":
    unittest.main()
