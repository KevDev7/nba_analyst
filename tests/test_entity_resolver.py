from __future__ import annotations

import unittest

from apps.cli.entity_resolver import (
    EntityResolutionError,
    enrich_semantic_draft_with_resolved_entities,
)


class EntityResolverTests(unittest.TestCase):
    def test_resolves_unique_last_name_against_combined_player_name_set(self) -> None:
        draft = {
            "task": "compare",
            "subject": "players",
            "measure": "points",
            "time_window": {"kind": "last_n_games", "value": 10},
            "entities": ["Brunson", "Haliburton"],
        }

        enriched = enrich_semantic_draft_with_resolved_entities(draft)

        self.assertEqual(
            enriched["resolved_entities"],
            [
                {"entityId": 1628973, "entityName": "Jalen Brunson"},
                {"entityId": 1630169, "entityName": "Tyrese Haliburton"},
            ],
        )
        self.assertEqual(
            enriched["value_resolution_trace"]["entity_resolutions"],
            [
                {
                    "raw_value": "Brunson",
                    "canonical_value": "Jalen Brunson",
                    "target_object": "Player",
                    "attribute": "full_name",
                    "entity_id": 1628973,
                    "source": "duckdb_entity_resolver",
                },
                {
                    "raw_value": "Haliburton",
                    "canonical_value": "Tyrese Haliburton",
                    "target_object": "Player",
                    "attribute": "full_name",
                    "entity_id": 1630169,
                    "source": "duckdb_entity_resolver",
                },
            ],
        )

    def test_resolves_unique_first_name_when_combined_first_last_set_is_unique(self) -> None:
        draft = {
            "task": "compare",
            "subject": "players",
            "measure": "points",
            "time_window": {"kind": "last_n_games", "value": 10},
            "entities": ["LeBron", "Tatum"],
        }

        enriched = enrich_semantic_draft_with_resolved_entities(draft)

        self.assertEqual(enriched["resolved_entities"][0]["entityName"], "LeBron James")
        self.assertEqual(enriched["resolved_entities"][1]["entityName"], "Jayson Tatum")

    def test_rejects_ambiguous_single_token_player_name(self) -> None:
        draft = {
            "task": "compare",
            "subject": "players",
            "measure": "points",
            "time_window": {"kind": "last_n_games", "value": 10},
            "entities": ["Jalen", "Tatum"],
        }

        with self.assertRaises(EntityResolutionError) as context:
            enrich_semantic_draft_with_resolved_entities(draft)

        self.assertIn("ambiguous", str(context.exception))


if __name__ == "__main__":
    unittest.main()
