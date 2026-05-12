from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from apps.assistant.tools.python_analysis import PythonAnalysisToolRequest, run
from runtime.AnalysisTools.local_worker import run_analysis_request
from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn


def prior_team_points_table() -> AnalysisTable:
    return AnalysisTable(
        id="q_2023_24.primary",
        title="2023-24 team average points",
        columns=[
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="avg_points", label="2023-24 Avg Points", type="number"),
        ],
        rows=[
            {"team": "Pacers", "avg_points": 123.3},
            {"team": "Celtics", "avg_points": 120.6},
            {"team": "Magic", "avg_points": 110.5},
        ],
        metadata={"source_query_id": "q_2023_24"},
    )


def current_team_points_table() -> AnalysisTable:
    return AnalysisTable(
        id="q_2024_25.primary",
        title="2024-25 team average points",
        columns=[
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="avg_points", label="2024-25 Avg Points", type="number"),
        ],
        rows=[
            {"team": "Pacers", "avg_points": 117.4},
            {"team": "Celtics", "avg_points": 116.3},
            {"team": "Magic", "avg_points": 116.1},
        ],
        metadata={"source_query_id": "q_2024_25"},
    )


class PythonAnalysisToolTests(unittest.TestCase):
    def test_join_and_delta_computes_current_minus_prior_table(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[prior_team_points_table(), current_team_points_table()],
                operation={
                    "kind": "join_and_delta",
                    "left_table_id": "q_2023_24.primary",
                    "right_table_id": "q_2024_25.primary",
                    "join_keys": ["team"],
                    "left_metric": "avg_points",
                    "right_metric": "avg_points",
                    "left_output_column": "avg_points_2023_24",
                    "right_output_column": "avg_points_2024_25",
                    "output_metric": "increase",
                    "sort": {"by": "increase", "direction": "desc"},
                    "title": "Biggest increases in team average points per game",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.tables), 1)
        table = result.tables[0]
        self.assertEqual(table.metadata["operation_kind"], "join_and_delta")
        self.assertEqual(table.metadata["calculation"], "right_metric_minus_left_metric")
        self.assertEqual(table.rows[0]["team"], "Magic")
        self.assertAlmostEqual(table.rows[0]["increase"], 5.6)
        self.assertEqual(table.rows[-1]["team"], "Pacers")
        self.assertAlmostEqual(table.rows[-1]["increase"], -5.9)
        self.assertEqual(result.findings[0].evidence_table_id, table.id)
        self.assertEqual(result.findings[0].row_refs, [0])

    def test_rank_extremes_sorts_and_adds_rank_column(self) -> None:
        delta_table = AnalysisTable(
            id="analysis.delta",
            title="Team deltas",
            columns=[
                AnalysisTableColumn(id="team", label="Team", type="text"),
                AnalysisTableColumn(id="increase", label="Increase", type="number"),
            ],
            rows=[
                {"team": "Pacers", "increase": -5.9},
                {"team": "Celtics", "increase": -4.3},
                {"team": "Magic", "increase": 5.6},
            ],
        )

        result = run_analysis_request(
            AnalysisRequest(
                tables=[delta_table],
                operation={
                    "kind": "rank_extremes",
                    "input_table_id": "analysis.delta",
                    "metric": "increase",
                    "direction": "desc",
                    "limit": 2,
                },
            )
        )

        self.assertTrue(result.ok)
        table = result.tables[0]
        self.assertEqual([row["rank"] for row in table.rows], [1, 2])
        self.assertEqual([row["team"] for row in table.rows], ["Magic", "Celtics"])
        self.assertEqual(table.metadata["parent_table_ids"], ["analysis.delta"])

    def test_assistant_python_analysis_wrapper_returns_outputs_and_provenance(self) -> None:
        result = run(
            PythonAnalysisToolRequest(
                request_id="analysis_test",
                analysis_request=AnalysisRequest(
                    tables=[prior_team_points_table(), current_team_points_table()],
                    operation={
                        "kind": "join_and_delta",
                        "left_table_id": "q_2023_24.primary",
                        "right_table_id": "q_2024_25.primary",
                        "join_keys": ["team"],
                        "left_metric": "avg_points",
                        "right_metric": "avg_points",
                        "output_metric": "increase",
                    },
                ),
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.analysis_id, "analysis_test")
        self.assertEqual(result.provenance["tool"], "python_analysis.run")
        self.assertEqual(result.provenance["operation_kind"], "join_and_delta")
        self.assertEqual(result.provenance["parent_table_ids"], ["q_2023_24.primary", "q_2024_25.primary"])
        self.assertEqual(result.provenance["derived_from_table_ids"], ["q_2023_24.primary", "q_2024_25.primary"])
        self.assertEqual(result.provenance["output_table_ids"], ["q_2023_24.primary_q_2024_25.primary_increase"])
        self.assertEqual(len(result.outputs["tables"]), 1)
        self.assertEqual(result.outputs["tables"][0]["metadata"]["parent_table_ids"], ["q_2023_24.primary", "q_2024_25.primary"])


if __name__ == "__main__":
    unittest.main()
