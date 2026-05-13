from __future__ import annotations

import unittest

from apps.assistant.model_orchestration.answer_composer import compose_grounded_answer


class AnswerComposerTests(unittest.TestCase):
    def _delta_table(self) -> dict[str, object]:
        return {
            "id": "delta_table",
            "columns": [{"id": "entity"}, {"id": "delta"}],
            "rows": [{"entity": "Grizzlies", "delta": 15.9}],
        }

    def test_composer_accepts_claims_with_valid_evidence(self) -> None:
        table = self._delta_table()

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
        table = self._delta_table()

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

    def test_composer_falls_back_when_numeric_claim_mismatches_evidence(self) -> None:
        answer = compose_grounded_answer(
            question="Who improved most?",
            evidence_tables=[self._delta_table()],
            findings=[],
            artifacts=[],
            fallback_answer="Fallback",
            call_model=lambda _prompt: """
            {
              "answer": "The Grizzlies improved by 99.9.",
              "claims": [
                {
                  "text": "The Grizzlies improved by 99.9.",
                  "evidence_refs": [{"table_id": "delta_table", "row_index": 0, "columns": ["entity", "delta"]}]
                }
              ],
              "limitations": []
            }
            """,
        )

        self.assertEqual(answer.answer, "Fallback")
        self.assertEqual(answer.claims, [])

    def test_composer_falls_back_when_entity_claim_mismatches_evidence(self) -> None:
        answer = compose_grounded_answer(
            question="Who improved most?",
            evidence_tables=[self._delta_table()],
            findings=[],
            artifacts=[],
            fallback_answer="Fallback",
            call_model=lambda _prompt: """
            {
              "answer": "The Lakers improved by 15.9.",
              "claims": [
                {
                  "text": "The Lakers improved by 15.9.",
                  "evidence_refs": [{"table_id": "delta_table", "row_index": 0, "columns": ["entity", "delta"]}]
                }
              ],
              "limitations": []
            }
            """,
        )

        self.assertEqual(answer.answer, "Fallback")
        self.assertEqual(answer.claims, [])

    def test_composer_falls_back_when_answer_number_mismatches_evidence(self) -> None:
        answer = compose_grounded_answer(
            question="Who improved most?",
            evidence_tables=[self._delta_table()],
            findings=[],
            artifacts=[],
            fallback_answer="Fallback",
            call_model=lambda _prompt: """
            {
              "answer": "The Grizzlies improved by 99.9.",
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

        self.assertEqual(answer.answer, "Fallback")
        self.assertEqual(answer.claims, [])

    def test_composer_falls_back_on_unsupported_causal_language(self) -> None:
        answer = compose_grounded_answer(
            question="Who improved most and why?",
            evidence_tables=[self._delta_table()],
            findings=[],
            artifacts=[],
            fallback_answer="Fallback",
            call_model=lambda _prompt: """
            {
              "answer": "The Grizzlies improved because of shooting.",
              "claims": [
                {
                  "text": "The Grizzlies improved because of shooting.",
                  "evidence_refs": [{"table_id": "delta_table", "row_index": 0, "columns": ["entity", "delta"]}]
                }
              ],
              "limitations": []
            }
            """,
        )

        self.assertEqual(answer.answer, "Fallback")
        self.assertEqual(answer.claims, [])

    def test_composer_retries_once_after_invalid_claim(self) -> None:
        responses = iter(
            [
                """
                {
                  "answer": "The Lakers improved by 15.9.",
                  "claims": [
                    {
                      "text": "The Lakers improved by 15.9.",
                      "evidence_refs": [{"table_id": "delta_table", "row_index": 0, "columns": ["entity", "delta"]}]
                    }
                  ],
                  "limitations": []
                }
                """,
                """
                {
                  "answer": "The Grizzlies improved by 15.9.",
                  "claims": [
                    {
                      "text": "The Grizzlies improved by 15.9.",
                      "evidence_refs": [{"table_id": "delta_table", "row_index": 0, "columns": ["entity", "delta"]}]
                    }
                  ],
                  "limitations": []
                }
                """,
            ]
        )

        answer = compose_grounded_answer(
            question="Who improved most?",
            evidence_tables=[self._delta_table()],
            findings=[],
            artifacts=[],
            fallback_answer="Fallback",
            call_model=lambda _prompt: next(responses),
        )

        self.assertEqual(answer.answer, "The Grizzlies improved by 15.9.")


if __name__ == "__main__":
    unittest.main()
