from __future__ import annotations

import unittest

from scripts.audit_semantic_metric_quality import audit_metric_quality, render_markdown


def columns_by_status(object_audit: dict[str, object], status: str) -> set[str]:
    return {
        str(column["column"])
        for column in object_audit["columns"]
        if column["status"] == status
    }


class SemanticMetricQualityAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = audit_metric_quality()

    def test_team_game_exposes_populated_boxscore_metrics_and_defers_rate_surfaces(self) -> None:
        team_game = self.audit["objects"]["TeamGame"]
        exposed = columns_by_status(team_game, "exposed")
        deferred = columns_by_status(team_game, "deferred_quality")

        self.assertEqual(team_game["counts"]["missing_data"], 0)
        self.assertEqual(team_game["counts"]["unexpected_unexposed"], 0)
        self.assertIn("assists", exposed)
        self.assertIn("total_rebounds", exposed)
        self.assertIn("steals", exposed)
        self.assertIn("blocks", exposed)
        self.assertIn("offensive_rating", exposed)
        self.assertIn("defensive_rating", exposed)
        self.assertIn("net_rating", exposed)
        self.assertIn("pace", deferred)
        self.assertIn("field_goals_percentage", deferred)
        self.assertIn("true_shooting_percentage", deferred)
        self.assertIn("assist_to_turnover_ratio", deferred)

    def test_team_season_exposes_all_populated_measure_metrics(self) -> None:
        team_season = self.audit["objects"]["TeamSeason"]
        exposed = columns_by_status(team_season, "exposed")

        self.assertEqual(team_season["counts"]["missing_data"], 0)
        self.assertEqual(team_season["counts"]["deferred_quality"], 0)
        self.assertEqual(team_season["counts"]["unexpected_unexposed"], 0)
        self.assertIn("assists_total", exposed)
        self.assertIn("rebounds_total", exposed)
        self.assertIn("true_shooting_percentage", exposed)
        self.assertIn("pace", exposed)

    def test_markdown_report_surfaces_deferred_quality_columns(self) -> None:
        markdown = render_markdown(self.audit)

        self.assertIn("# Semantic Metric Quality Audit", markdown)
        self.assertIn("## TeamGame", markdown)
        self.assertIn("- unexpected unexposed: 0", markdown)
        self.assertIn("### Deferred Quality Columns", markdown)
        self.assertIn("| pace |", markdown)
        self.assertIn("TeamGame rate, percentage, pace, and ratio metrics", markdown)


if __name__ == "__main__":
    unittest.main()
