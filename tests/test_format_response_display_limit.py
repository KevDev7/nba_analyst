from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisRuntime.models import (
    AggregateRow,
    ObjectRow,
    RankingRow,
    TimeSeriesRow,
)
from runtime.AnswerSynthesis.format_response import DISPLAY_ROW_LIMIT, format_response
from runtime.AnswerSynthesis.response_models import FinalAnswer
from tests.answer_context_helpers import build_final_answer


def base_answer(**overrides: object) -> FinalAnswer:
    values = {
        "summary": "Rows are shown below.",
        "interpretation": "Rows by metric.",
        "query_kind": "metric_query",
        "result_shape": "ranking",
        "entity_label_singular": "Player",
        "entity_label_plural": "Players",
        "context_label": "Team",
        "metric": "total_points",
        "window_games": 10,
        "limit": 0,
        "rows": [],
    }
    values.update(overrides)
    return build_final_answer(**values)


class FormatResponseDisplayLimitTests(unittest.TestCase):
    def test_ranking_output_displays_at_most_50_rows(self) -> None:
        answer = base_answer(
            rows=[
                RankingRow(rank=index, entity_name=f"Player {index}", metric_value=index)
                for index in range(1, DISPLAY_ROW_LIMIT + 2)
            ]
        )

        formatted = format_response(answer)

        self.assertIn(f"Showing first {DISPLAY_ROW_LIMIT} of {DISPLAY_ROW_LIMIT + 1} rows.", formatted)
        self.assertIn(f"{DISPLAY_ROW_LIMIT} | Player {DISPLAY_ROW_LIMIT} | {DISPLAY_ROW_LIMIT}", formatted)
        self.assertNotIn(f"{DISPLAY_ROW_LIMIT + 1} | Player {DISPLAY_ROW_LIMIT + 1}", formatted)
        self.assertEqual(len(answer.rows), DISPLAY_ROW_LIMIT + 1)

    def test_exactly_50_rows_has_no_display_notice(self) -> None:
        answer = base_answer(
            rows=[
                RankingRow(rank=index, entity_name=f"Player {index}", metric_value=index)
                for index in range(1, DISPLAY_ROW_LIMIT + 1)
            ]
        )

        formatted = format_response(answer)

        self.assertNotIn("Showing first", formatted)
        self.assertIn(f"{DISPLAY_ROW_LIMIT} | Player {DISPLAY_ROW_LIMIT} | {DISPLAY_ROW_LIMIT}", formatted)

    def test_object_rows_output_displays_at_most_50_rows(self) -> None:
        answer = base_answer(
            query_kind="object_query",
            result_shape="object_rows",
            rows=[],
            object_rows=[
                ObjectRow(entity_id=index, entity_name=f"Player {index}", metric_value=index)
                for index in range(1, DISPLAY_ROW_LIMIT + 2)
            ],
        )

        formatted = format_response(answer)

        self.assertIn(f"Showing first {DISPLAY_ROW_LIMIT} of {DISPLAY_ROW_LIMIT + 1} rows.", formatted)
        self.assertIn(f"Player {DISPLAY_ROW_LIMIT} | {DISPLAY_ROW_LIMIT}", formatted)
        self.assertNotIn(f"Player {DISPLAY_ROW_LIMIT + 1} | {DISPLAY_ROW_LIMIT + 1}", formatted)
        self.assertEqual(len(answer.object_rows), DISPLAY_ROW_LIMIT + 1)

    def test_aggregate_output_displays_at_most_50_rows(self) -> None:
        answer = base_answer(
            result_shape="aggregate",
            rows=[],
            aggregate_rows=[
                AggregateRow(entity_name=f"Team {index}", metric_value=index)
                for index in range(1, DISPLAY_ROW_LIMIT + 2)
            ],
        )

        formatted = format_response(answer)

        self.assertIn(f"Showing first {DISPLAY_ROW_LIMIT} of {DISPLAY_ROW_LIMIT + 1} rows.", formatted)
        self.assertIn(f"Team {DISPLAY_ROW_LIMIT} | {DISPLAY_ROW_LIMIT}", formatted)
        self.assertNotIn(f"Team {DISPLAY_ROW_LIMIT + 1} | {DISPLAY_ROW_LIMIT + 1}", formatted)

    def test_time_series_output_displays_at_most_50_rows(self) -> None:
        answer = base_answer(
            result_shape="time_series",
            rows=[],
            time_grain="day",
            time_series_rows=[
                TimeSeriesRow(time_bucket=f"2026-01-{index:02d}", metric_value=index)
                for index in range(1, DISPLAY_ROW_LIMIT + 2)
            ],
        )

        formatted = format_response(answer)

        self.assertIn(f"Showing first {DISPLAY_ROW_LIMIT} of {DISPLAY_ROW_LIMIT + 1} rows.", formatted)
        self.assertIn(f"2026-01-{DISPLAY_ROW_LIMIT:02d} | {DISPLAY_ROW_LIMIT}", formatted)
        self.assertNotIn(f"2026-01-{DISPLAY_ROW_LIMIT + 1:02d} | {DISPLAY_ROW_LIMIT + 1}", formatted)

    def test_find_rows_output_displays_at_most_50_rows(self) -> None:
        answer = base_answer(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            rows=[],
            find_rows=[
                {"game_id": index, "game_date": f"2026-01-{index:02d}"}
                for index in range(1, DISPLAY_ROW_LIMIT + 2)
            ],
        )

        formatted = format_response(answer)

        self.assertIn(f"Showing first {DISPLAY_ROW_LIMIT} of {DISPLAY_ROW_LIMIT + 1} rows.", formatted)
        self.assertIn(f"{DISPLAY_ROW_LIMIT} | 2026-01-{DISPLAY_ROW_LIMIT:02d}", formatted)
        self.assertNotIn(f"{DISPLAY_ROW_LIMIT + 1} | 2026-01-{DISPLAY_ROW_LIMIT + 1:02d}", formatted)
        self.assertEqual(len(answer.find_rows), DISPLAY_ROW_LIMIT + 1)


if __name__ == "__main__":
    unittest.main()
