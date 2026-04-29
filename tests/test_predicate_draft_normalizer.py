from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.assistant.pipeline import plan_question
from apps.cli.predicate_draft_normalizer import normalize_flat_filter_predicates
from apps.cli.semantic_interpreter import interpret_question_to_semantic_draft


def rank_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "rank",
        "subject": "players",
        "measure": "average points",
        "measures": ["average points"],
        "dimensions": [],
        "filters": [],
        "result_filters": [],
        "time_window": {"kind": "last_n_games", "value": 10},
        "grain": None,
        "order": [{"by": "average points", "direction": "desc"}],
        "limit": 5,
        "sort": "desc",
        "entities": [],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


class PredicateDraftNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_flat_list_and_range_filters_become_row_predicate_tree(self) -> None:
        normalized = normalize_flat_filter_predicates(
            rank_draft(
                filters=[
                    {"field": "team", "op": "in", "value": ["Lakers", "Warriors"]},
                    {"field": "minutes", "op": "between", "value": {"lower": 20, "upper": 30}},
                ]
            )
        )

        self.assertEqual(normalized["filters"], [])
        self.assertEqual(
            normalized["predicate"],
            {
                "kind": "and",
                "predicates": [
                    {"kind": "leaf", "field": "team", "op": "in", "value": ["Lakers", "Warriors"]},
                    {"kind": "leaf", "field": "minutes", "op": "between", "value": {"lower": 20, "upper": 30}},
                ],
            },
        )

    def test_duplicate_flat_equality_filters_become_in_predicate(self) -> None:
        normalized = normalize_flat_filter_predicates(
            rank_draft(
                filters=[
                    {"field": "team", "op": "=", "value": "Lakers"},
                    {"field": "team", "op": "=", "value": "Warriors"},
                ]
            )
        )

        self.assertEqual(normalized["filters"], [])
        self.assertEqual(
            normalized["predicate"],
            {"kind": "leaf", "field": "team", "op": "in", "value": ["Lakers", "Warriors"]},
        )

    def test_time_scope_filters_stay_in_filter_lane(self) -> None:
        normalized = normalize_flat_filter_predicates(
            rank_draft(
                filters=[
                    {"field": "season type", "op": "=", "value": "regular season"},
                    {"field": "team", "op": "in", "value": ["Lakers", "Warriors"]},
                ]
            )
        )

        self.assertEqual(
            normalized["filters"],
            [{"field": "season type", "op": "=", "value": "regular season"}],
        )
        self.assertEqual(
            normalized["predicate"],
            {"kind": "leaf", "field": "team", "op": "in", "value": ["Lakers", "Warriors"]},
        )

    def test_existing_predicate_is_combined_with_promoted_flat_filter(self) -> None:
        normalized = normalize_flat_filter_predicates(
            rank_draft(
                predicate={"kind": "leaf", "field": "conference", "op": "=", "value": "West"},
                filters=[{"field": "team", "op": "in", "value": ["Lakers", "Warriors"]}],
            )
        )

        self.assertEqual(normalized["predicate"]["kind"], "and")
        self.assertEqual(len(normalized["predicate"]["predicates"]), 2)

    def test_result_filter_range_becomes_result_predicate(self) -> None:
        normalized = normalize_flat_filter_predicates(
            rank_draft(
                result_filters=[
                    {"field": "average points", "op": "between", "value": {"lower": 20, "upper": 30}},
                ]
            )
        )

        self.assertEqual(normalized["result_filters"], [])
        self.assertEqual(
            normalized["result_predicate"],
            {"kind": "leaf", "field": "average points", "op": "between", "value": {"lower": 20, "upper": 30}},
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_pipeline_plans_llm_flat_list_and_range_filters(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": rank_draft(
                    filters=[
                        {"field": "team", "op": "in", "value": ["Lakers", "Warriors"]},
                        {"field": "minutes", "op": "between", "value": {"lower": 20, "upper": 30}},
                    ]
                ),
            }
        )

        semantic_draft, planner_output = plan_question(
            "Rank players on the Lakers or Warriors by average points with minutes between 20 and 30 over the last 10 games"
        )
        sql = planner_output["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(semantic_draft["filters"], [])
        self.assertEqual(semantic_draft["predicate"]["kind"], "and")
        self.assertIn("lf1.team_name IN ('Lakers', 'Warriors')", sql)
        self.assertIn("f.minutes_played BETWEEN 20 AND 30", sql)

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_pipeline_plans_llm_flat_result_range_filter(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": rank_draft(
                    result_filters=[
                        {"field": "average points", "op": "between", "value": {"lower": 20, "upper": 30}},
                    ]
                ),
            }
        )

        semantic_draft, planner_output = plan_question(
            "Rank players by average points over the last 10 games where average points are between 20 and 30"
        )
        sql = planner_output["execution_plan"]["steps"][0]["sql"]

        self.assertEqual(semantic_draft["result_filters"], [])
        self.assertEqual(semantic_draft["result_predicate"]["op"], "between")
        self.assertIn("metric_value BETWEEN 20 AND 30", sql)


if __name__ == "__main__":
    unittest.main()
