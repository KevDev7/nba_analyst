from __future__ import annotations

import unittest

from scripts.generate_semantic_value_aliases import (
    ambiguous_aliases,
    build_team_value_aliases,
    merge_aliases,
)


class SemanticValueAliasGeneratorTests(unittest.TestCase):
    def test_builds_team_aliases_from_snapshot_rows_without_city_only_aliases(self) -> None:
        aliases = build_team_value_aliases(
            [
                ("Lakers", "Los Angeles", "LAL", "west", "pacific"),
                ("Clippers", "Los Angeles", "LAC", "west", "pacific"),
            ]
        )

        self.assertEqual(
            aliases["Team"]["team_name"]["Lakers"],
            ["Lakers", "LAL", "Los Angeles Lakers"],
        )
        self.assertEqual(
            aliases["Team"]["team_abbreviation"]["LAL"],
            ["LAL", "Lakers", "Los Angeles Lakers"],
        )
        self.assertNotIn("Los Angeles", aliases["Team"]["team_name"]["Lakers"])
        self.assertEqual(aliases["Team"]["conference"]["west"], ["west", "west conference", "western", "western conference"])
        self.assertEqual(aliases["Team"]["division"]["pacific"], ["pacific", "pacific division"])

    def test_curated_aliases_layer_only_non_derivable_aliases(self) -> None:
        data_aliases = build_team_value_aliases(
            [("Cavaliers", "Cleveland", "CLE", "east", "central")]
        )
        aliases = merge_aliases(
            data_aliases,
            {"Team": {"team_name": {"Cavaliers": ["Cavs"]}}},
        )

        self.assertEqual(
            aliases["Team"]["team_name"]["Cavaliers"],
            ["Cavaliers", "CLE", "Cleveland Cavaliers", "Cavs"],
        )

    def test_curated_dimension_value_aliases_preserve_boolean_canonical_text(self) -> None:
        aliases = merge_aliases(
            {},
            {
                "PlayerGame": {
                    "team_home_or_away": {
                        "away": ["road", "on the road"],
                    },
                    "is_starter": {
                        "true": ["starter"],
                        "false": ["bench", "off the bench"],
                    },
                }
            },
        )

        self.assertEqual(aliases["PlayerGame"]["team_home_or_away"]["away"], ["road", "on the road"])
        self.assertEqual(aliases["PlayerGame"]["is_starter"]["true"], ["starter"])
        self.assertEqual(aliases["PlayerGame"]["is_starter"]["false"], ["bench", "off the bench"])

    def test_detects_ambiguous_aliases_before_ontology_generation(self) -> None:
        aliases = {
            "Team": {
                "team_name": {
                    "Lakers": ["LA"],
                    "Clippers": ["LA"],
                }
            }
        }

        self.assertEqual(
            ambiguous_aliases(aliases),
            {("Team", "team_name", "la"): ["Clippers", "Lakers"]},
        )


if __name__ == "__main__":
    unittest.main()
