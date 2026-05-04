from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.assistant.pipeline import plan_question
from apps.assistant.semantic.assumptions import apply_semantic_assumptions


def season_rank_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "rank",
        "subject": "players",
        "measure": "average points",
        "measures": ["average points"],
        "dimensions": [],
        "filters": [],
        "time_window": {"kind": "season", "value": None},
        "grain": None,
        "order": [],
        "limit": 10,
        "sort": "desc",
        "entities": [],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


def find_games_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "find",
        "subject": "games",
        "measure": None,
        "measures": [],
        "dimensions": [],
        "filters": [
            {"field": "team", "op": "=", "value": "Lakers"},
            {"field": "score", "op": ">", "value": 120},
        ],
        "time_window": None,
        "grain": None,
        "order": [],
        "limit": 5,
        "sort": None,
        "entities": ["Lakers"],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


def compare_players_draft(**overrides: object) -> dict[str, object]:
    draft: dict[str, object] = {
        "task": "compare",
        "subject": "players",
        "measure": "points",
        "measures": ["points"],
        "dimensions": [],
        "filters": [],
        "result_filters": [],
        "time_window": None,
        "grain": None,
        "order": [],
        "limit": None,
        "sort": None,
        "entities": ["Jalen Brunson", "Jayson Tatum"],
        "operations": [],
        "assumptions": [],
    }
    draft.update(overrides)
    return draft


class SemanticAssumptionTests(unittest.TestCase):
    def test_entity_row_language_reconciles_rank_draft_to_object(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show me the top 5 players and their total points for the Knicks over the last 10 games",
            season_rank_draft(
                measure="total points",
                measures=["total points"],
                filters=[{"field": "team", "op": "=", "value": "Knicks"}],
                time_window={"kind": "last_n_games", "value": 10},
                limit=5,
            ),
        )

        self.assertEqual(enriched["task"], "object")
        self.assertEqual(enriched["limit"], 5)
        self.assertEqual(enriched["sort"], "desc")
        self.assertEqual(enriched["filters"], [{"field": "team", "op": "=", "value": "Knicks"}])

    def test_metric_first_by_language_stays_rank(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show me the top 5 players by total points for the Knicks over the last 10 games",
            season_rank_draft(
                measure="total points",
                measures=["total points"],
                filters=[{"field": "team", "op": "=", "value": "Knicks"}],
                time_window={"kind": "last_n_games", "value": 10},
                limit=5,
            ),
        )

        self.assertEqual(enriched["task"], "rank")

    def test_season_grain_language_does_not_default_to_current_season(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show year over year team wins",
            season_rank_draft(
                task="trend",
                subject="teams",
                measure="wins",
                measures=["wins"],
                dimensions=["team"],
                time_window={"kind": "all", "value": None},
                grain="season",
                limit=None,
            ),
        )

        self.assertEqual(enriched["time_window"], {"kind": "all", "value": None})
        self.assertEqual(enriched["grain"], "season")
        self.assertEqual(enriched["filters"], [])
        self.assertEqual(enriched["assumptions"], [])

    def test_scoring_totals_adds_grounded_user_facing_assumption(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show me players with their scoring totals over the last 10 games",
            season_rank_draft(
                task="object",
                measure="scoring totals",
                measures=["scoring totals"],
                time_window={"kind": "last_n_games", "value": 10},
                assumptions=[],
            ),
        )

        self.assertEqual(enriched["task"], "object")
        self.assertEqual(enriched["assumptions"], ["Interpreted 'scoring' as total points."])

    def test_average_scoring_adds_grounded_user_facing_assumption(self) -> None:
        enriched = apply_semantic_assumptions(
            "Who has the highest average scoring over the last 10 games?",
            season_rank_draft(
                measure="average scoring",
                measures=["average scoring"],
                time_window={"kind": "last_n_games", "value": 10},
                limit=1,
                assumptions=["Interpreted 'highest' as a request for the top 1 player."],
            ),
        )

        self.assertIn("Interpreted 'average scoring' as average points.", enriched["assumptions"])

    def test_explicit_year_and_explicit_type_are_preserved_without_assumptions(self) -> None:
        draft = season_rank_draft(
            time_window={"kind": "season", "value": "2025-26"},
        )

        enriched = apply_semantic_assumptions(
            "Show me players by average points in the 2025-26 regular season",
            draft,
        )

        self.assertEqual(enriched["time_window"], {"kind": "season", "value": "2025-26"})
        self.assertEqual(
            enriched["filters"],
            [{"field": "season type", "op": "=", "value": "regular season"}],
        )
        self.assertEqual(enriched["assumptions"], [])

    def test_explicit_year_missing_type_defaults_regular_season(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show me players by average points in the 2025-26 season",
            season_rank_draft(time_window={"kind": "season", "value": "2025-26"}),
        )

        self.assertEqual(enriched["time_window"], {"kind": "season", "value": "2025-26"})
        self.assertEqual(
            enriched["filters"],
            [{"field": "season type", "op": "=", "value": "regular season"}],
        )
        self.assertEqual(enriched["assumptions"], ["Assumed season type is regular season."])

    def test_missing_year_explicit_type_defaults_current_season_year(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show me players by average points in the regular season",
            season_rank_draft(),
        )

        self.assertEqual(enriched["time_window"], {"kind": "season", "value": "2025-26"})
        self.assertEqual(
            enriched["filters"],
            [{"field": "season type", "op": "=", "value": "regular season"}],
        )
        self.assertEqual(enriched["assumptions"], ["Assumed season year is 2025-26."])

    def test_missing_year_and_type_default_together(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show me players by average points this season",
            season_rank_draft(time_window={"kind": "this season", "value": None}),
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

    def test_this_season_can_recover_from_unspecified_llm_window(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show me players by average points this season",
            season_rank_draft(time_window={"kind": "unspecified", "value": None}),
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

    def test_cross_season_trend_is_not_narrowed_to_default_year(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show team wins by season across all seasons",
            season_rank_draft(
                task="trend",
                subject="teams",
                measure="wins",
                time_window={"kind": "all", "value": None},
                grain="season",
            ),
        )

        self.assertEqual(enriched["time_window"], {"kind": "all", "value": None})
        self.assertEqual(enriched["filters"], [])
        self.assertEqual(enriched["assumptions"], [])

    def test_short_explicit_season_year_is_expanded_without_default_assumption(self) -> None:
        enriched = apply_semantic_assumptions(
            "What is Curry points per game in the 24-25 regular season?",
            season_rank_draft(time_window={"kind": "season", "value": None}),
        )

        self.assertEqual(enriched["time_window"], {"kind": "season", "value": "2024-25"})
        self.assertEqual(enriched["assumptions"], [])

    def test_last_n_games_query_is_not_silently_narrowed_to_default_season(self) -> None:
        draft = season_rank_draft(time_window={"kind": "last_n_games", "value": 10})

        enriched = apply_semantic_assumptions(
            "Show me top 10 players by points over the last 10 games",
            draft,
        )

        self.assertEqual(enriched["time_window"], {"kind": "last_n_games", "value": 10})
        self.assertEqual(enriched["filters"], [])
        self.assertEqual(enriched["assumptions"], [])

    def test_recent_query_with_explicit_short_season_preserves_both_constraints(self) -> None:
        enriched = apply_semantic_assumptions(
            "What is Stephen Curry points per game the last 8 games in the 24-25 season?",
            season_rank_draft(time_window={"kind": "last_n_games", "value": 8}),
        )

        self.assertEqual(enriched["time_window"], {"kind": "last_n_games", "value": 8})
        self.assertEqual(
            enriched["filters"],
            [
                {"field": "season", "op": "=", "value": "2024-25"},
                {"field": "season type", "op": "=", "value": "regular season"},
            ],
        )
        self.assertEqual(enriched["assumptions"], ["Assumed season type is regular season."])

    def test_recent_query_with_explicit_season_type_does_not_add_type_assumption(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show me top players by points over the last 8 games in the 2024-25 playoffs",
            season_rank_draft(time_window={"kind": "last_n_games", "value": 8}),
        )

        self.assertEqual(enriched["time_window"], {"kind": "last_n_games", "value": 8})
        self.assertEqual(
            enriched["filters"],
            [
                {"field": "season", "op": "=", "value": "2024-25"},
                {"field": "season type", "op": "=", "value": "playoffs"},
            ],
        )
        self.assertEqual(enriched["assumptions"], [])

    def test_find_null_time_window_defaults_to_all_available_data(self) -> None:
        enriched = apply_semantic_assumptions(
            "Find games where the Lakers scored over 120 points",
            find_games_draft(),
        )

        self.assertEqual(enriched["time_window"], {"kind": "all", "value": None})
        self.assertEqual(
            enriched["assumptions"],
            ["Used all available data in the local snapshot: 2020-21 through 2025-26."],
        )

    def test_find_missing_time_window_defaults_to_all_available_data(self) -> None:
        draft = find_games_draft()
        del draft["time_window"]

        enriched = apply_semantic_assumptions(
            "Find games where the Lakers scored over 120 points",
            draft,
        )

        self.assertEqual(enriched["time_window"], {"kind": "all", "value": None})

    def test_find_unspecified_time_window_defaults_to_all_available_data(self) -> None:
        enriched = apply_semantic_assumptions(
            "Find games where the Lakers scored over 120 points",
            find_games_draft(time_window={"kind": "unspecified", "value": None}),
        )

        self.assertEqual(enriched["time_window"], {"kind": "all", "value": None})

    def test_find_all_games_wording_overrides_bad_season_window(self) -> None:
        enriched = apply_semantic_assumptions(
            "Find games where the Lakers scored over 120 points over all games",
            find_games_draft(
                time_window={"kind": "season", "value": None},
                assumptions=["Interpreted 'all games' as the current season."],
            ),
        )

        self.assertEqual(enriched["time_window"], {"kind": "all", "value": None})
        self.assertEqual(
            enriched["assumptions"],
            ["Used all available data in the local snapshot: 2020-21 through 2025-26."],
        )
        self.assertNotIn(
            {"field": "season type", "op": "=", "value": "regular season"},
            enriched["filters"],
        )

    def test_find_last_n_games_is_preserved(self) -> None:
        enriched = apply_semantic_assumptions(
            "Find Lakers games over the last 10 games",
            find_games_draft(time_window={"kind": "last_n_games", "value": 10}),
        )

        self.assertEqual(enriched["time_window"], {"kind": "last_n_games", "value": 10})
        self.assertEqual(enriched["assumptions"], [])

    def test_compare_missing_time_scope_defaults_to_current_regular_season(self) -> None:
        enriched = apply_semantic_assumptions(
            "Compare Jalen Brunson and Jayson Tatum points",
            compare_players_draft(),
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

    def test_compare_explicit_recent_time_scope_is_preserved(self) -> None:
        enriched = apply_semantic_assumptions(
            "Compare Jalen Brunson and Jayson Tatum points over the last 10 games",
            compare_players_draft(time_window={"kind": "last_n_games", "value": 10}),
        )

        self.assertEqual(enriched["time_window"], {"kind": "last_n_games", "value": 10})
        self.assertEqual(enriched["filters"], [])
        self.assertEqual(enriched["assumptions"], [])

    def test_natural_between_dates_normalize_to_canonical_time_window(self) -> None:
        enriched = apply_semantic_assumptions(
            "Find Lakers games between Jan 1 and Feb 1 2025",
            find_games_draft(time_window={"kind": "all", "value": None}),
        )

        self.assertEqual(
            enriched["time_window"],
            {"kind": "between_dates", "value": "2025-01-01 to 2025-02-01"},
        )

    def test_yearless_since_date_is_not_guessed(self) -> None:
        enriched = apply_semantic_assumptions(
            "Show monthly team wins since Jan 1",
            season_rank_draft(
                task="trend",
                subject="teams",
                measure="wins",
                time_window={"kind": "all", "value": None},
                grain="month",
            ),
        )

        self.assertEqual(enriched["time_window"], {"kind": "all", "value": None})

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_pipeline_applies_assumptions_before_haskell_planning(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {
                "status": "ok",
                "draft": season_rank_draft(time_window={"kind": "season", "value": None}),
            }
        )

        semantic_draft, planner_output = plan_question(
            "Show me players by average points this season"
        )

        self.assertEqual(semantic_draft["time_window"], {"kind": "season", "value": "2025-26"})
        self.assertEqual(
            semantic_draft["filters"],
            [{"field": "season type", "op": "=", "value": "regular season"}],
        )
        self.assertEqual(
            semantic_draft["assumptions"],
            [
                "Assumed season year is 2025-26.",
                "Assumed season type is regular season.",
            ],
        )
        self.assertEqual(
            planner_output["query"]["spec"]["sharedQuery"]["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(
            planner_output["execution_plan"]["assumptions"],
            [
                "Assumed season year is 2025-26.",
                "Assumed season type is regular season.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
