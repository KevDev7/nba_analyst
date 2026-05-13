from __future__ import annotations

import unittest

from apps.assistant.workspace import RunWorkspace
from runtime.AnalysisTools.models import AnalysisFinding, AnalysisTable, AnalysisTableColumn


def _table(table_id: str = "sq.primary") -> AnalysisTable:
    return AnalysisTable(
        id=table_id,
        title="Test table",
        columns=[
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="points", label="Points", type="number"),
        ],
        rows=[{"team": "Thunder", "points": 120.0}],
    )


class RunWorkspaceTests(unittest.TestCase):
    def test_workspace_stores_and_resolves_tables_with_trace_links(self) -> None:
        workspace = RunWorkspace()
        workspace.add_table(
            _table(),
            source_tool_call_id="tc_1",
            source_tool_name="semantic_query.plan_execute",
            metadata={"query_id": "sq_1"},
        )

        self.assertEqual(workspace.resolve_table("sq.primary").rows[0]["team"], "Thunder")
        links = workspace.resource_trace_links()
        self.assertEqual(links[0]["resource_id"], "sq.primary")
        self.assertEqual(links[0]["source_tool_call_id"], "tc_1")

    def test_workspace_rejects_unknown_table_ids(self) -> None:
        workspace = RunWorkspace()

        with self.assertRaisesRegex(ValueError, "Unknown or unapproved table id"):
            workspace.resolve_table("missing")

    def test_workspace_records_artifacts_and_findings(self) -> None:
        workspace = RunWorkspace()
        artifact_id = workspace.add_artifact(
            {"kind": "chart", "id": "chart_1", "title": "Chart"},
            source_tool_call_id="tc_chart",
            source_tool_name="chart_generation.run",
            parent_ids=["sq.primary"],
        )
        finding_id = workspace.add_finding(
            AnalysisFinding(kind="note", text="Finding", evidence_table_id="sq.primary", row_refs=[0]),
            source_tool_call_id="tc_analysis",
            source_tool_name="python_analysis.run",
            parent_ids=["sq.primary"],
        )

        self.assertEqual(artifact_id, "chart_1")
        self.assertEqual(finding_id, "finding_1")
        self.assertEqual(workspace.provenance["chart_1"].parent_ids, ["sq.primary"])


if __name__ == "__main__":
    unittest.main()
