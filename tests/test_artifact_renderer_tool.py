from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from apps.assistant.tools.artifact_renderer import ArtifactRenderRequest, render
from runtime.AnalysisTools.models import AnalysisTable, AnalysisTableColumn
from runtime.AnalysisRuntime.models import RankingRow
from tests.answer_context_helpers import build_final_answer


class ArtifactRendererToolTests(unittest.TestCase):
    def test_render_builds_current_text_chart_table_artifacts(self) -> None:
        answer = build_final_answer(
            summary="Top scorers are shown below.",
            interpretation="Players ranked by total points.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="total_points",
            window_games=10,
            limit=2,
            rows=[
                RankingRow(rank=1, entity_name="Jalen Brunson", context_value="NYK", metric_value=312),
                RankingRow(rank=2, entity_name="Jayson Tatum", context_value="BOS", metric_value=298),
            ],
        )

        result = render(ArtifactRenderRequest(question="Show the ranking as a chart", answer=answer))

        self.assertTrue(result.ok)
        self.assertEqual([artifact["kind"] for artifact in result.artifacts], ["text", "text", "chart", "table"])
        self.assertEqual(result.artifact_count, 4)
        self.assertEqual(result.artifacts[2]["metadata"]["operation_kind"], "bar_chart")
        self.assertEqual(result.provenance["chart_bridge"], "apps.assistant.chart_artifacts.append_chart_artifacts")

    def test_render_can_return_table_only_when_requested(self) -> None:
        answer = build_final_answer(
            summary="Top scorers are shown below.",
            interpretation="Players ranked by total points.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="total_points",
            window_games=10,
            limit=1,
            rows=[
                RankingRow(rank=1, entity_name="Jalen Brunson", context_value="NYK", metric_value=312),
            ],
        )

        result = render(
            ArtifactRenderRequest(
                question="Give me the table only",
                answer=answer,
                allowed_artifact_kinds=["table"],
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual([artifact["kind"] for artifact in result.artifacts], ["table"])
        self.assertEqual(result.artifacts[0]["row_count"], 1)

    def test_render_can_project_analysis_tables(self) -> None:
        table = AnalysisTable(
            id="analysis.delta",
            title="Team deltas",
            columns=[
                AnalysisTableColumn(id="entity", label="Team", type="text"),
                AnalysisTableColumn(id="delta", label="Delta", type="number"),
            ],
            rows=[{"entity": "Magic", "delta": 5.6}],
            row_count=1,
            metadata={"operation_kind": "join_and_delta"},
        )

        result = render(
            ArtifactRenderRequest(
                question="Which teams improved most?",
                tables=[table],
                summary="Biggest increases",
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual([artifact["kind"] for artifact in result.artifacts], ["text", "text", "table"])
        self.assertEqual(result.artifacts[2]["metadata"]["source_table_id"], "analysis.delta")
        self.assertEqual(result.artifacts[2]["rows"][0]["entity"], "Magic")


if __name__ == "__main__":
    unittest.main()
