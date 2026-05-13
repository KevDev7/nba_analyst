from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisTools.local_worker import run_analysis_request
from runtime.AnalysisTools.models import AnalysisRequest, AnalysisTable, AnalysisTableColumn


def sample_monthly_table() -> AnalysisTable:
    return AnalysisTable(
        id="monthly_team_points",
        title="Monthly team points",
        columns=[
            AnalysisTableColumn(id="month", label="Month", type="date"),
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="average_points", label="Average Points", type="number"),
        ],
        rows=[
            {"month": "2026-01", "team": "Lakers", "average_points": 118.4},
            {"month": "2026-02", "team": "Lakers", "average_points": 120.1},
            {"month": "2026-01", "team": "Warriors", "average_points": 116.9},
        ],
    )


def sample_player_ranking_table() -> AnalysisTable:
    return AnalysisTable(
        id="player_points",
        title="Player points",
        columns=[
            AnalysisTableColumn(id="rank", label="Rank", type="integer"),
            AnalysisTableColumn(id="player", label="Player", type="text"),
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="total_points", label="Total Points", type="number"),
        ],
        rows=[
            {"rank": 1, "player": "Jalen Brunson", "team": "NYK", "total_points": 312},
            {"rank": 2, "player": "Jayson Tatum", "team": "BOS", "total_points": 298},
            {"rank": 3, "player": "Anthony Edwards", "team": "MIN", "total_points": 287},
        ],
    )


def sample_player_metric_table() -> AnalysisTable:
    return AnalysisTable(
        id="player_metrics",
        title="Player metrics",
        columns=[
            AnalysisTableColumn(id="player", label="Player", type="text"),
            AnalysisTableColumn(id="team", label="Team", type="text"),
            AnalysisTableColumn(id="points", label="Points", type="number"),
            AnalysisTableColumn(id="assists", label="Assists", type="number"),
        ],
        rows=[
            {"player": "Jalen Brunson", "team": "NYK", "points": 312, "assists": 74},
            {"player": "Jayson Tatum", "team": "BOS", "points": 298, "assists": 81},
        ],
    )


def sample_player_assist_table() -> AnalysisTable:
    return AnalysisTable(
        id="player_assists",
        title="Player assists",
        columns=[
            AnalysisTableColumn(id="player", label="Player", type="text"),
            AnalysisTableColumn(id="assists", label="Assists", type="number"),
        ],
        rows=[
            {"player": "A", "assists": 10},
            {"player": "B", "assists": 20},
            {"player": "C", "assists": 30},
        ],
    )


def sample_player_points_table() -> AnalysisTable:
    return AnalysisTable(
        id="player_points",
        title="Player points",
        columns=[
            AnalysisTableColumn(id="player", label="Player", type="text"),
            AnalysisTableColumn(id="points", label="Points", type="number"),
        ],
        rows=[
            {"player": "A", "points": 1},
            {"player": "B", "points": 2},
            {"player": "C", "points": 3},
        ],
    )


class LocalAnalysisWorkerTests(unittest.TestCase):
    def test_line_chart_operation_returns_vega_lite_artifact(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_monthly_table()],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "month",
                    "y": "average_points",
                    "series": "team",
                    "title": "Monthly average points by team",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.artifacts), 1)
        artifact = result.artifacts[0]
        self.assertEqual(artifact.kind, "chart")
        self.assertEqual(artifact.renderer, "vega_lite")
        self.assertEqual(artifact.title, "Monthly average points by team")
        self.assertEqual(artifact.spec["width"], "container")
        self.assertEqual(artifact.spec["height"], 360)
        self.assertEqual(
            artifact.spec["autosize"],
            {"contains": "padding", "resize": True, "type": "fit-x"},
        )
        self.assertEqual(artifact.spec["mark"]["type"], "line")
        self.assertTrue(artifact.spec["mark"]["point"])
        self.assertEqual(artifact.spec["encoding"]["x"]["field"], "month")
        self.assertEqual(artifact.spec["encoding"]["x"]["type"], "temporal")
        self.assertEqual(artifact.spec["encoding"]["y"]["field"], "average_points")
        self.assertEqual(artifact.spec["encoding"]["y"]["type"], "quantitative")
        self.assertEqual(artifact.spec["encoding"]["color"]["field"], "team")
        self.assertIn("datasets", artifact.spec)
        chart_rows = next(iter(artifact.spec["datasets"].values()))
        self.assertEqual(chart_rows[0]["month"], "2026-01-01T00:00:00")
        self.assertEqual(artifact.metadata["source_table_id"], "monthly_team_points")
        self.assertEqual(artifact.metadata["chart_family"], "line")
        self.assertEqual(artifact.metadata["x_type"], "date")
        self.assertEqual(artifact.metadata["y_type"], "number")
        self.assertEqual(artifact.metadata["series_count"], 2)
        self.assertEqual(artifact.metadata["category_count"], 0)
        self.assertEqual(artifact.data["row_count"], 3)

    def test_bar_chart_operation_returns_bar_mark(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_monthly_table()],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "team",
                    "y": "average_points",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.artifacts[0].spec["mark"]["type"], "bar")
        self.assertEqual(result.artifacts[0].spec["encoding"]["x"]["field"], "team")
        self.assertEqual(result.artifacts[0].metadata["chart_family"], "bar")
        self.assertEqual(result.artifacts[0].metadata["series_count"], 0)
        self.assertEqual(result.artifacts[0].metadata["category_count"], 2)

    def test_point_chart_operation_returns_point_mark(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_player_metric_table()],
                operation={
                    "kind": "point_chart",
                    "input_table_id": "player_metrics",
                    "x": "points",
                    "y": "assists",
                    "title": "Points and assists",
                },
            )
        )

        self.assertTrue(result.ok)
        artifact = result.artifacts[0]
        self.assertEqual(artifact.spec["mark"]["type"], "point")
        self.assertTrue(artifact.spec["mark"]["filled"])
        self.assertEqual(artifact.spec["encoding"]["x"]["field"], "points")
        self.assertEqual(artifact.spec["encoding"]["x"]["type"], "quantitative")
        self.assertEqual(artifact.spec["encoding"]["y"]["field"], "assists")
        self.assertEqual(artifact.spec["encoding"]["y"]["type"], "quantitative")
        self.assertNotIn("color", artifact.spec["encoding"])
        self.assertEqual(artifact.metadata["chart_family"], "point")
        self.assertEqual(artifact.metadata["operation_kind"], "point_chart")
        tooltip_fields = [tooltip["field"] for tooltip in artifact.spec["encoding"]["tooltip"]]
        self.assertEqual(tooltip_fields, ["player", "team", "points", "assists"])

    def test_correlation_operation_returns_known_result_table(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_player_points_table(), sample_player_assist_table()],
                operation={
                    "kind": "correlation",
                    "left_table_id": "player_points",
                    "right_table_id": "player_assists",
                    "join_keys": ["player"],
                    "left_metric": "points",
                    "right_metric": "assists",
                    "method": "pearson",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.tables), 1)
        table = result.tables[0]
        self.assertEqual(table.rows[0]["correlation"], 1.0)
        self.assertEqual(table.rows[0]["paired_row_count"], 3)
        self.assertEqual(table.metadata["operation_kind"], "correlation")
        self.assertEqual(result.findings[0].evidence_table_id, table.id)

    def test_horizontal_bar_chart_sorts_category_axis_by_rank(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_player_ranking_table()],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "player_points",
                    "x": "total_points",
                    "y": "player",
                    "orientation": "horizontal",
                    "sort": {"channel": "y", "field": "rank", "order": "ascending"},
                },
            )
        )

        self.assertTrue(result.ok)
        artifact = result.artifacts[0]
        self.assertEqual(artifact.spec["mark"]["type"], "bar")
        self.assertEqual(artifact.spec["encoding"]["x"]["field"], "total_points")
        self.assertEqual(artifact.spec["encoding"]["x"]["type"], "quantitative")
        self.assertEqual(artifact.spec["encoding"]["y"]["field"], "player")
        self.assertEqual(artifact.spec["encoding"]["y"]["type"], "nominal")
        self.assertEqual(artifact.spec["encoding"]["y"]["sort"]["field"], "rank")
        self.assertEqual(artifact.spec["encoding"]["y"]["sort"]["order"], "ascending")
        self.assertEqual(artifact.metadata["orientation"], "horizontal")
        self.assertEqual(artifact.metadata["x_type"], "number")
        self.assertEqual(artifact.metadata["y_type"], "text")
        self.assertEqual(artifact.metadata["category_count"], 3)

    def test_chart_operation_metadata_is_preserved_with_worker_fields_canonical(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_player_ranking_table()],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "player_points",
                    "x": "total_points",
                    "y": "player",
                    "orientation": "horizontal",
                    "metadata": {
                        "source_result_shape": "ranking",
                        "row_count": 999,
                    },
                },
            )
        )

        self.assertTrue(result.ok)
        artifact = result.artifacts[0]
        self.assertEqual(artifact.metadata["source_result_shape"], "ranking")
        self.assertEqual(artifact.metadata["row_count"], 3)

    def test_horizontal_bar_chart_allows_source_order_without_sorting(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_player_ranking_table()],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "player_points",
                    "x": "total_points",
                    "y": "player",
                    "orientation": "horizontal",
                    "sort": {"channel": "y", "field": None, "order": None},
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertIsNone(result.artifacts[0].spec["encoding"]["y"]["sort"])

    def test_tooltip_only_date_range_does_not_block_horizontal_bar_chart(self) -> None:
        table = AnalysisTable(
            id="player_points",
            title="Player points",
            columns=[
                AnalysisTableColumn(id="rank", label="Rank", type="integer"),
                AnalysisTableColumn(id="player", label="Player", type="text"),
                AnalysisTableColumn(id="date_range", label="Date Range", type="date"),
                AnalysisTableColumn(id="total_points", label="Total Points", type="number"),
            ],
            rows=[
                {
                    "rank": 1,
                    "player": "Jalen Brunson",
                    "date_range": "2026-03-10 to 2026-03-27",
                    "total_points": 312,
                },
                {
                    "rank": 2,
                    "player": "Jayson Tatum",
                    "date_range": "2026-03-12 to 2026-03-30",
                    "total_points": 298,
                },
            ],
        )

        result = run_analysis_request(
            AnalysisRequest(
                tables=[table],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "player_points",
                    "x": "total_points",
                    "y": "player",
                    "orientation": "horizontal",
                    "sort": {"channel": "y", "field": "rank", "order": "ascending"},
                },
            )
        )

        self.assertTrue(result.ok)
        artifact = result.artifacts[0]
        tooltip = artifact.spec["encoding"]["tooltip"]
        date_range_tooltip = next(item for item in tooltip if item["field"] == "date_range")
        self.assertEqual(date_range_tooltip["type"], "nominal")
        chart_rows = next(iter(artifact.spec["datasets"].values()))
        self.assertEqual(chart_rows[0]["date_range"], "2026-03-10 to 2026-03-27")

    def test_unsupported_renderer_returns_structured_error(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_monthly_table()],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "month",
                    "y": "average_points",
                    "renderer": "plotly",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code if result.error else None, "unsupported_renderer")
        self.assertEqual(result.logs[0].level, "error")

    def test_non_numeric_y_axis_returns_structured_error(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_monthly_table()],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "monthly_team_points",
                    "x": "month",
                    "y": "team",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "invalid_chart_operation")
        self.assertIn("must be numeric", result.error.message if result.error else "")

    def test_horizontal_bar_chart_requires_numeric_x_axis(self) -> None:
        result = run_analysis_request(
            AnalysisRequest(
                tables=[sample_player_ranking_table()],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "player_points",
                    "x": "player",
                    "y": "total_points",
                    "orientation": "horizontal",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "invalid_chart_operation")
        self.assertIn("must be numeric", result.error.message if result.error else "")

    def test_invalid_numeric_values_return_structured_error(self) -> None:
        bad_table = AnalysisTable(
            id="bad_points",
            columns=[
                AnalysisTableColumn(id="team", label="Team", type="text"),
                AnalysisTableColumn(id="average_points", label="Average Points", type="number"),
            ],
            rows=[{"team": "Lakers", "average_points": "not a number"}],
        )

        result = run_analysis_request(
            AnalysisRequest(
                tables=[bad_table],
                operation={
                    "kind": "bar_chart",
                    "input_table_id": "bad_points",
                    "x": "team",
                    "y": "average_points",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "invalid_numeric_column")

    def test_invalid_temporal_values_return_structured_error(self) -> None:
        bad_table = AnalysisTable(
            id="bad_months",
            columns=[
                AnalysisTableColumn(id="month", label="Month", type="date"),
                AnalysisTableColumn(id="average_points", label="Average Points", type="number"),
            ],
            rows=[{"month": "not a month", "average_points": 118.4}],
        )

        result = run_analysis_request(
            AnalysisRequest(
                tables=[bad_table],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "bad_months",
                    "x": "month",
                    "y": "average_points",
                },
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code if result.error else None, "invalid_temporal_column")

    def test_empty_table_still_returns_empty_chart_artifact(self) -> None:
        empty_table = AnalysisTable(
            id="empty_monthly_points",
            columns=[
                AnalysisTableColumn(id="month", label="Month", type="date"),
                AnalysisTableColumn(id="average_points", label="Average Points", type="number"),
            ],
            rows=[],
        )

        result = run_analysis_request(
            AnalysisRequest(
                tables=[empty_table],
                operation={
                    "kind": "line_chart",
                    "input_table_id": "empty_monthly_points",
                    "x": "month",
                    "y": "average_points",
                },
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.artifacts[0].data["row_count"], 0)
        self.assertEqual(result.artifacts[0].spec["encoding"]["x"]["type"], "temporal")
        self.assertEqual(result.artifacts[0].spec["encoding"]["y"]["type"], "quantitative")


if __name__ == "__main__":
    unittest.main()
