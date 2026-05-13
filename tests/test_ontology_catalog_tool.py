from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.assistant.tools.ontology_catalog import OntologyCatalogRequest, inspect


class OntologyCatalogToolTests(unittest.TestCase):
    def test_inspect_returns_ontology_and_snapshot_coverage(self) -> None:
        result = inspect(OntologyCatalogRequest(facets=["subjects", "fact_surfaces", "coverage"], max_items=20))

        self.assertTrue(result.ok)
        self.assertIsNotNone(result.ontology_version)
        self.assertTrue(result.ontology_version.startswith("semantic-gold:"))
        self.assertIsNotNone(result.data_snapshot_id)
        self.assertIn("2025-26", result.coverage["seasons"])
        self.assertEqual(result.coverage["default_season"], "2025-26")
        self.assertEqual(result.coverage["default_season_type"], "regular_season")
        self.assertEqual(result.coverage["lowest_grain"], "game")
        self.assertIn("play_by_play", result.coverage["unsupported_surfaces"])
        self.assertTrue(any(subject["key"] == "Team" for subject in result.subjects))
        self.assertFalse(any(subject["key"] == "TeamGame" for subject in result.subjects))
        self.assertTrue(any(surface["key"] == "TeamGame" for surface in result.fact_surfaces))
        team_game = next(surface for surface in result.fact_surfaces if surface["key"] == "TeamGame")
        self.assertEqual(team_game["subject"], "Team")
        self.assertEqual(team_game["grain"], "game")

    def test_inspect_can_search_metrics_with_aliases(self) -> None:
        result = inspect(
            OntologyCatalogRequest(
                facets=["metrics"],
                subject_hint="teams",
                search="net rating",
                include_aliases=True,
            )
        )

        self.assertTrue(result.ok)
        metric_keys = {metric["key"] for metric in result.metrics}
        self.assertIn("average_net_rating", metric_keys)
        metric = next(metric for metric in result.metrics if metric["key"] == "average_net_rating")
        self.assertEqual(metric["ranking_polarity"], "higher_is_better")
        self.assertIn("net rating", metric["aliases"])

    def test_inspect_filters_facets_without_limitations(self) -> None:
        result = inspect(
            OntologyCatalogRequest(
                facets=["time_grains"],
                subject_hint="player games",
                include_limitations=False,
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.subjects, [])
        self.assertEqual(result.metrics, [])
        self.assertEqual(result.limitations, [])
        grain_keys = {grain["key"] for grain in result.time_grains}
        self.assertIn("game_date", grain_keys)
        self.assertIn("game_year_month", grain_keys)

    @patch("apps.assistant.tools.ontology_catalog._load_haskell_catalog", return_value=None)
    def test_inspect_falls_back_to_python_yaml_catalog(self, _mock_haskell_catalog) -> None:
        result = inspect(OntologyCatalogRequest(facets=["subjects", "metrics"], subject_hint="teams"))

        self.assertTrue(result.ok)
        self.assertTrue(any(subject["key"] == "Team" for subject in result.subjects))
        self.assertTrue(any(metric["key"] == "average_net_rating" for metric in result.metrics))


if __name__ == "__main__":
    unittest.main()
