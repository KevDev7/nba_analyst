from __future__ import annotations

import unittest

from apps.assistant.model_orchestration.answer_composer import compose_grounded_answer


class AnswerComposerTests(unittest.TestCase):
    def test_composer_accepts_claims_with_valid_evidence(self) -> None:
        table = {
            "id": "delta_table",
            "columns": [{"id": "entity"}, {"id": "delta"}],
            "rows": [{"entity": "Grizzlies", "delta": 15.9}],
        }

        answer = compose_grounded_answer(
            question="Who improved most?",
            evidence_tables=[table],
            findings=[],
            artifacts=[],
            fallback_answer="Fallback",
            call_model=lambda _prompt: """
            {
              "answer": "The Grizzlies improved the most, up 15.9.",
              "claims": [
                {
                  "text": "The Grizzlies improved by 15.9.",
                  "evidence_refs": [{"table_id": "delta_table", "row_index": 0, "columns": ["entity", "delta"]}]
                }
              ],
              "limitations": []
            }
            """,
        )

        self.assertEqual(answer.answer, "The Grizzlies improved the most, up 15.9.")
        self.assertEqual(answer.claims[0].evidence_refs[0].table_id, "delta_table")

    def test_composer_falls_back_when_claim_lacks_valid_evidence(self) -> None:
        table = {
            "id": "delta_table",
            "columns": [{"id": "entity"}, {"id": "delta"}],
            "rows": [{"entity": "Grizzlies", "delta": 15.9}],
        }

        answer = compose_grounded_answer(
            question="Who improved most?",
            evidence_tables=[table],
            findings=[],
            artifacts=[],
            fallback_answer="Fallback",
            call_model=lambda _prompt: """
            {
              "answer": "The Grizzlies improved the most, up 15.9.",
              "claims": [
                {
                  "text": "The Grizzlies improved by 15.9.",
                  "evidence_refs": [{"table_id": "missing", "row_index": 0, "columns": ["delta"]}]
                }
              ],
              "limitations": []
            }
            """,
        )

        self.assertEqual(answer.answer, "Fallback")
        self.assertEqual(answer.claims, [])


if __name__ == "__main__":
    unittest.main()
