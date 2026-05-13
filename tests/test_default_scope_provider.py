from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.assistant.semantic.default_scope import (
    FALLBACK_DEFAULT_SEASON_TYPE,
    FALLBACK_DEFAULT_SEASON_YEAR,
    DefaultTimeScope,
    get_default_time_scope,
)
from apps.assistant.semantic.assumptions import apply_semantic_assumptions
from tests.test_semantic_assumptions import season_rank_draft


class DefaultScopeProviderTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_default_time_scope.cache_clear()

    def test_snapshot_default_matches_current_product_default(self) -> None:
        get_default_time_scope.cache_clear()

        scope = get_default_time_scope()

        self.assertEqual(scope.season_year, FALLBACK_DEFAULT_SEASON_YEAR)
        self.assertEqual(scope.season_type, FALLBACK_DEFAULT_SEASON_TYPE)
        self.assertEqual(scope.source, "snapshot_metadata")

    @patch("apps.assistant.semantic.default_scope.load_database", side_effect=RuntimeError("missing snapshot"))
    def test_fallback_constants_used_when_snapshot_metadata_unavailable(self, _mock_load_database) -> None:
        get_default_time_scope.cache_clear()

        scope = get_default_time_scope()

        self.assertEqual(scope.season_year, FALLBACK_DEFAULT_SEASON_YEAR)
        self.assertEqual(scope.season_type, FALLBACK_DEFAULT_SEASON_TYPE)
        self.assertEqual(scope.source, "fallback_constants")

    @patch(
        "apps.assistant.semantic.assumptions.get_default_time_scope",
        return_value=DefaultTimeScope(
            season_year="2025-26",
            season_type="regular_season",
            source="snapshot_metadata",
        ),
    )
    def test_semantic_assumptions_read_defaults_from_provider(self, mock_default_scope) -> None:
        enriched = apply_semantic_assumptions(
            "Show me players by average points this season",
            season_rank_draft(time_window={"kind": "season", "value": None}),
        )

        self.assertEqual(enriched["time_window"], {"kind": "season", "value": "2025-26"})
        self.assertEqual(
            enriched["filters"],
            [{"field": "season type", "op": "=", "value": "regular season"}],
        )
        self.assertEqual(
            enriched["assumptions"],
            [
                "Assumed season year is 2025-26.",
                "Assumed season type is regular season.",
            ],
        )
        mock_default_scope.assert_called()


if __name__ == "__main__":
    unittest.main()
