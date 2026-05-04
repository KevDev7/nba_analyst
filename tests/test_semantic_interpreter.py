from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.assistant.semantic.interpreter import (
    SemanticInterpreterError,
    _semantic_draft_prompt_preamble,
    interpret_question_to_semantic_draft,
)


SAMPLE_DRAFT = {
    "task": "rank",
    "subject": "players",
    "measure": "points",
    "time_window": {"kind": "last_n_games", "value": 10},
    "limit": 10,
    "sort": "desc",
    "assumptions": [],
}


class SemanticInterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_prompt_requests_loose_draft_not_planner_ir(self) -> None:
        prompt = _semantic_draft_prompt_preamble()

        self.assertIn("loose semantic draft", prompt)
        self.assertIn('"rank" | "trend" | "aggregate" | "find" | "compare" | "object"', prompt)
        self.assertIn('"operations"', prompt)
        self.assertIn("positive integer", prompt)
        self.assertNotIn('"limit": 10 | 5 | 1 | null', prompt)
        self.assertIn("Do not output ontology object names", prompt)
        self.assertIn('"draft"', prompt)
        self.assertNotIn('"coreFactObject"', prompt)
        self.assertNotIn('"query_kind"', prompt)
        self.assertNotIn("Capability summary", prompt)
        self.assertIn('"task":"object"', prompt)
        self.assertIn("row-level constraints", prompt)
        self.assertIn('"field":"minutes","op":">","value":30', prompt)
        self.assertIn('"field":"win percentage","op":">","value":0.6', prompt)
        self.assertIn('"rank_intent"', prompt)
        self.assertIn("Do not decide metric polarity", prompt)
        self.assertIn("Who has the best defensive rating this season?", prompt)
        self.assertIn('"team home or away"', prompt)
        self.assertIn('"is starter"', prompt)
        self.assertIn('"conference"', prompt)
        self.assertIn('"season type"', prompt)
        self.assertIn("bench scorers", prompt)
        self.assertIn("on the road", prompt)
        self.assertIn("postseason", prompt)
        self.assertIn("Do not invent a time_window kind for playoffs or postseason", prompt)
        self.assertIn("Time grain rules", prompt)
        self.assertIn("month over month", prompt)
        self.assertIn("week over week", prompt)
        self.assertIn("season by season", prompt)
        self.assertIn("year over year", prompt)
        self.assertIn('"grain":"season"', prompt)
        self.assertIn("Game log rules", prompt)
        self.assertIn("game by game stats", prompt)
        self.assertIn("last N games log", prompt)
        self.assertIn("Show Jalen Brunson's game log over his last 10 games", prompt)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_returns_basic_validated_semantic_draft(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": SAMPLE_DRAFT})

        draft = interpret_question_to_semantic_draft(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(draft["task"], SAMPLE_DRAFT["task"])
        self.assertEqual(draft["subject"], SAMPLE_DRAFT["subject"])
        self.assertEqual(draft["measure"], SAMPLE_DRAFT["measure"])
        self.assertEqual(draft["time_window"], SAMPLE_DRAFT["time_window"])
        self.assertEqual(draft["limit"], SAMPLE_DRAFT["limit"])
        sent_prompt = mock_call_gemini.call_args.args[0]
        self.assertIn("User question:", sent_prompt)
        self.assertIn("top 10 players", sent_prompt)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_preserves_rank_intent_without_sort_direction(self, mock_call_gemini) -> None:
        draft = dict(SAMPLE_DRAFT)
        draft["measure"] = "defensive rating"
        draft["measures"] = ["defensive rating"]
        draft["sort"] = None
        draft["rank_intent"] = "best"
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft("Who has the best defensive rating this season?")

        self.assertEqual(interpreted["rank_intent"], "best")
        self.assertIsNone(interpreted["sort"])

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_tolerates_extra_trailing_close_braces(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": SAMPLE_DRAFT}) + "\n}\n}\n"

        draft = interpret_question_to_semantic_draft(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(draft["measure"], "points")

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_raises_for_non_analytics_unsupported_response(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps(
            {"status": "unsupported", "reason": "not an NBA analytics request"}
        )

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_semantic_draft("Write me a birthday card")

        self.assertIn("not an NBA analytics request", str(context.exception))

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_does_not_gate_time_window_capabilities(self, mock_call_gemini) -> None:
        draft = dict(SAMPLE_DRAFT)
        draft["time_window"] = {"kind": "last_month", "value": 1}
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft(
            "Show me the top 10 players by points over the last month"
        )

        self.assertEqual(interpreted["time_window"], {"kind": "last_month", "value": 1})

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_allows_find_null_time_window_for_policy_normalization(self, mock_call_gemini) -> None:
        draft = {
            "task": "find",
            "subject": "games",
            "measure": None,
            "measures": [],
            "dimensions": [],
            "filters": [{"field": "team", "op": "=", "value": "Lakers"}],
            "time_window": None,
            "grain": None,
            "order": [],
            "limit": None,
            "sort": None,
            "entities": ["Lakers"],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft(
            "Find games where the Lakers scored over 120 points"
        )

        self.assertIsNone(interpreted["time_window"])

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_allows_compare_null_time_window_for_default_scope(self, mock_call_gemini) -> None:
        draft = {
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
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft(
            "Compare Jalen Brunson and Jayson Tatum points"
        )

        self.assertIsNone(interpreted["time_window"])

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_preserves_decimal_numeric_filter_values(self, mock_call_gemini) -> None:
        draft = {
            "task": "rank",
            "subject": "teams",
            "measure": "wins",
            "measures": ["wins"],
            "dimensions": [],
            "filters": [{"field": "win percentage", "op": ">", "value": 0.6}],
            "time_window": {"kind": "season", "value": "2025-26"},
            "grain": None,
            "order": [{"by": "wins", "direction": "desc"}],
            "limit": None,
            "sort": "desc",
            "entities": [],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft(
            "Show me teams by wins with win percentage above .600 in the 2025-26 season"
        )

        self.assertEqual(
            interpreted["filters"],
            [{"field": "win percentage", "op": ">", "value": 0.6}],
        )

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_preserves_contextual_value_phrase_filters(self, mock_call_gemini) -> None:
        draft = {
            "task": "rank",
            "subject": "players",
            "measure": "scoring",
            "measures": ["scoring"],
            "dimensions": [],
            "filters": [
                {"field": "is starter", "op": "=", "value": "bench"},
                {"field": "team home or away", "op": "=", "value": "road"},
                {"field": "conference", "op": "=", "value": "east"},
                {"field": "season type", "op": "=", "value": "playoffs"},
            ],
            "time_window": {"kind": "season", "value": "2024-25"},
            "grain": None,
            "order": [{"by": "scoring", "direction": "desc"}],
            "limit": None,
            "sort": None,
            "rank_intent": "top",
            "entities": [],
            "operations": [],
            "assumptions": ["Interpreted 'scorers' as players ranked by points."],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft(
            "Top East road bench scorers in the 2024-25 postseason"
        )

        self.assertEqual(
            interpreted["filters"],
            [
                {"field": "is starter", "op": "=", "value": "bench"},
                {"field": "team home or away", "op": "=", "value": "road"},
                {"field": "conference", "op": "=", "value": "east"},
                {"field": "season type", "op": "=", "value": "playoffs"},
            ],
        )

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_preserves_calendar_and_season_grain_language(self, mock_call_gemini) -> None:
        draft = {
            "task": "trend",
            "subject": "teams",
            "measure": "net rating",
            "measures": ["net rating"],
            "dimensions": ["team"],
            "filters": [],
            "time_window": {"kind": "all", "value": None},
            "grain": "season",
            "order": [],
            "limit": None,
            "sort": None,
            "entities": [],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft(
            "Show year over year team net rating"
        )

        self.assertEqual(interpreted["task"], "trend")
        self.assertEqual(interpreted["time_window"], {"kind": "all", "value": None})
        self.assertEqual(interpreted["grain"], "season")
        self.assertEqual(interpreted["dimensions"], ["team"])

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_maps_game_by_game_recent_stats_to_find_rows(self, mock_call_gemini) -> None:
        draft = {
            "task": "find",
            "subject": "players",
            "measure": None,
            "measures": [],
            "dimensions": ["date", "team", "opponent", "points"],
            "filters": [{"field": "player", "op": "=", "value": "Jalen Brunson"}],
            "time_window": {"kind": "last_n_games", "value": 10},
            "grain": None,
            "order": [{"by": "date", "direction": "desc"}],
            "limit": None,
            "sort": None,
            "entities": ["Jalen Brunson"],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        interpreted = interpret_question_to_semantic_draft(
            "Show Jalen Brunson game by game points over his last 10 games"
        )

        self.assertEqual(interpreted["task"], "find")
        self.assertEqual(interpreted["subject"], "players")
        self.assertEqual(interpreted["dimensions"], ["date", "team", "opponent", "points"])
        self.assertEqual(interpreted["filters"], [{"field": "player", "op": "=", "value": "Jalen Brunson"}])
        self.assertEqual(interpreted["time_window"], {"kind": "last_n_games", "value": 10})
        self.assertIsNone(interpreted["grain"])
        self.assertEqual(interpreted["order"], [{"by": "date", "direction": "desc"}])

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_still_requires_non_find_time_window(self, mock_call_gemini) -> None:
        draft = dict(SAMPLE_DRAFT)
        draft["time_window"] = None
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": draft})

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_semantic_draft("Show me top 10 players by points")

        self.assertIn("time_window is required except for find drafts", str(context.exception))


if __name__ == "__main__":
    unittest.main()
