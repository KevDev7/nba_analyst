from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.assistant.tools.chart_generation import ChartGenerationRequest, run
from runtime.AnalysisTools.models import AnalysisTable, AnalysisTableColumn


def _team_table() -> AnalysisTable:
    return AnalysisTable(
        id="analysis.points",
        title="Team points",
        columns=[
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="points", label="Points", type="number"),
        ],
        rows=[
            {"team": "Thunder", "points": 120.0},
            {"team": "Celtics", "points": 118.0},
        ],
    )


class ChartGenerationToolTests(unittest.TestCase):
    def test_deterministic_chart_generation_returns_vega_lite_artifact(self) -> None:
        result = run(ChartGenerationRequest(tables=[_team_table()], chart_intent="bar chart of points by team"))

        self.assertTrue(result.ok)
        self.assertEqual(result.artifacts[0]["renderer"], "vega_lite")
        self.assertEqual(result.provenance["parent_table_ids"], ["analysis.points"])

    def test_unknown_renderer_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires vega_lite"):
            ChartGenerationRequest(tables=[_team_table()], allowed_renderers=["plotly"])

    def test_unknown_candidate_column_falls_back_to_deterministic(self) -> None:
        spec = {
            "mark": "bar",
            "encoding": {
                "x": {"field": "missing", "type": "nominal"},
                "y": {"field": "points", "type": "quantitative"},
            },
        }

        with patch.dict("os.environ", {"NBA_ENABLE_MODEL_CHART_GENERATION": "1"}):
            result = run(ChartGenerationRequest(tables=[_team_table()], generation_mode="model", candidate_spec=spec))

        self.assertTrue(result.ok)
        self.assertEqual(result.provenance["validation_status"], "fallback_validated")
        self.assertIn("fallback_reason", result.provenance)

    def test_model_candidate_spec_rejects_external_url_and_falls_back(self) -> None:
        spec = {
            "data": {"url": "https://example.com/data.json"},
            "mark": "bar",
            "encoding": {"x": {"field": "team"}, "y": {"field": "points"}},
        }

        with patch.dict("os.environ", {"NBA_ENABLE_MODEL_CHART_GENERATION": "1"}):
            result = run(ChartGenerationRequest(tables=[_team_table()], generation_mode="model", candidate_spec=spec))

        self.assertTrue(result.ok)
        self.assertEqual(result.provenance["generation_mode"], "deterministic")

    def test_sandbox_chart_code_rejects_database_capability(self) -> None:
        with self.assertRaisesRegex(ValueError, "forbidden SQL/database"):
            ChartGenerationRequest(
                tables=[_team_table()],
                generation_mode="sandbox",
                sandbox_code="import duckdb\noutputs = {}",
            )

    def test_result_does_not_include_raw_sql_or_private_debug(self) -> None:
        result = run(ChartGenerationRequest(tables=[_team_table()], chart_intent="chart"))
        payload = str(result.model_dump()).lower()

        self.assertNotIn("select ", payload)
        self.assertNotIn("private_debug", payload)


if __name__ == "__main__":
    unittest.main()
