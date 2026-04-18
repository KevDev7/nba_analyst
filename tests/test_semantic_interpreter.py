from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from apps.cli.semantic_interpreter import (
    ROOT,
    SemanticInterpreterError,
    _capability_artifact,
    _capability_prompt_summary,
    _interpreter_prompt_preamble,
    interpret_question_to_planner_query,
)
from scripts.generate_interpreter_capabilities import build_capability_artifact


class SemanticInterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_planner_query.cache_clear()
        _capability_artifact.cache_clear()
        _capability_prompt_summary.cache_clear()

    def test_generated_capability_artifact_matches_committed_fixture(self) -> None:
        generated = build_capability_artifact()
        committed = json.loads(
            (
                ROOT
                / "fixtures"
                / "interpreter"
                / "semantic-capabilities.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(generated, committed)

    def test_prompt_summary_is_sourced_from_generated_capability_artifact(self) -> None:
        artifact = _capability_artifact()
        summary = _capability_prompt_summary()

        self.assertIn(artifact["prompt_summary"], summary)
        self.assertIn(
            "Supported semantic families (generated from ontology + planner-derived capabilities):",
            summary,
        )
        self.assertIn("player_game_recent_object_player_team_filter", summary)
        self.assertNotIn("Current live supported semantic shapes:", summary)

    def test_execution_contract_is_now_only_an_exception_list(self) -> None:
        contract = (
            ROOT
            / "pipelines"
            / "athena"
            / "metadata"
            / "semantic_interpreter_execution_contract.yaml"
        ).read_text(encoding="utf-8")

        self.assertIn("planner-derived", contract)
        self.assertNotIn("\nfamilies:", contract)
        self.assertNotIn("comparison_entities", contract)

    def test_derived_family_for_knicks_object_query_now_allows_limit(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "object_query"
            and family["core_fact_object"] == "PlayerGame"
            and family["row_object"] == "Player"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["last_n_games"]
            and family["linked_filters"]
            and family["linked_filters"][0]["target_object"] == "Team"
            and family["linked_filters"][0]["attribute"] == "team_name"
            and "total_points" in family["metrics"]
        ]

        self.assertTrue(matching)
        self.assertTrue(any(family["allow_limit"] for family in matching))

    def test_derived_family_for_average_points_object_query_is_discovered(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "object_query"
            and family["core_fact_object"] == "PlayerGame"
            and family["row_object"] == "Player"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["last_n_games"]
            and not family["linked_filters"]
            and "average_points" in family["metrics"]
        ]

        self.assertTrue(matching)

    def test_misleading_player_game_season_team_filter_metric_family_is_not_derived(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "metric_query"
            and family["core_fact_object"] == "PlayerGame"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["exact_season", "season_type"]
            and family["linked_filters"]
            and family["linked_filters"][0]["target_object"] == "Team"
            and family["linked_filters"][0]["attribute"] == "team_name"
        ]

        self.assertEqual(matching, [])

    def test_player_season_team_season_team_filter_metric_family_remains_derived(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "metric_query"
            and family["core_fact_object"] == "PlayerSeasonTeam"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["exact_season", "season_type"]
            and family["linked_filters"]
            and family["linked_filters"][0]["target_object"] == "Team"
            and family["linked_filters"][0]["attribute"] == "team_name"
            and "average_points" in family["metrics"]
        ]

        self.assertTrue(matching)

    def test_player_game_season_object_team_filter_family_remains_derived(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "object_query"
            and family["core_fact_object"] == "PlayerGame"
            and family["row_object"] == "Player"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["exact_season", "season_type"]
            and family["linked_filters"]
            and family["linked_filters"][0]["target_object"] == "Team"
            and family["linked_filters"][0]["attribute"] == "team_name"
            and "total_points" in family["metrics"]
        ]

        self.assertTrue(matching)

    def test_player_season_team_season_object_team_filter_family_remains_derived(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["query_kind"] == "object_query"
            and family["core_fact_object"] == "PlayerSeasonTeam"
            and family["row_object"] == "Player"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["exact_season", "season_type"]
            and family["linked_filters"]
            and family["linked_filters"][0]["target_object"] == "Team"
            and family["linked_filters"][0]["attribute"] == "team_name"
            and "total_points" in family["metrics"]
        ]

        self.assertTrue(matching)

    def test_recent_player_name_total_points_comparison_family_remains_derived(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["comparison"]["enabled"]
            and family["core_fact_object"] == "PlayerGame"
            and family["dimensions"] == ["player_name"]
            and family["required_filter_kinds"] == ["last_n_games"]
            and family["metrics"] == ["total_points"]
        ]

        self.assertTrue(matching)

    def test_misleading_monthly_comparison_families_are_not_derived(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["comparison"]["enabled"] and family["time_grain"] == "month"
        ]

        self.assertEqual(matching, [])

    def test_misleading_non_player_name_comparison_families_are_not_derived(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["comparison"]["enabled"] and family["dimensions"] != ["player_name"]
        ]

        self.assertEqual(matching, [])

    def test_only_narrow_core_trend_families_remain_derived(self) -> None:
        artifact = _capability_artifact()
        trend_families = [
            family for family in artifact["families"] if family["time_grain"] == "month"
        ]

        self.assertEqual(len(trend_families), 2)
        self.assertEqual(
            {
                (
                    family["core_fact_object"],
                    tuple(family["dimensions"]),
                    tuple(family["required_filter_kinds"]),
                )
                for family in trend_families
            },
            {
                ("TeamGame", tuple(), ("past_year",)),
                ("TeamGame", ("team_name",), ("past_year",)),
            },
        )

    def test_misleading_player_game_trend_families_are_not_derived(self) -> None:
        artifact = _capability_artifact()
        matching = [
            family
            for family in artifact["families"]
            if family["time_grain"] == "month"
            and family["core_fact_object"] == "PlayerGame"
        ]

        self.assertEqual(matching, [])

    def test_trend_families_do_not_allow_limit(self) -> None:
        artifact = _capability_artifact()
        trend_families = [
            family for family in artifact["families"] if family["time_grain"] == "month"
        ]

        self.assertTrue(trend_families)
        self.assertTrue(all(not family["allow_limit"] for family in trend_families))

    def test_interpreter_prompt_no_longer_uses_trend_ambiguity_nudge(self) -> None:
        prompt = _interpreter_prompt_preamble()

        self.assertNotIn("temporary ambiguity nudge", prompt)
        self.assertNotIn("prefer the broad team-level aggregate path on TeamGame", prompt)

    def test_player_entity_index_is_generated_from_snapshot(self) -> None:
        artifact = _capability_artifact()
        player_index = artifact["player_entity_index"]

        self.assertIn("players", player_index)
        self.assertIn("aliases", player_index)
        self.assertIn("brunson", player_index["aliases"])
        self.assertEqual(
            player_index["aliases"]["brunson"]["player"]["player_name"], "Jalen Brunson"
        )
        self.assertEqual(player_index["aliases"]["jalen"]["status"], "ambiguous")

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_valid_metric_query_template_normalizes_to_haskell_query_json(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "orders": [{"kind": "desc", "metric": "total_points"}],
            "limit": 10,
            "entity_filters": [],
            "comparison": null,
            "assumptions": []
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        self.assertEqual(payload["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame")
        self.assertEqual(payload["spec"]["sharedQuery"]["metrics"], ["total_points"])
        self.assertEqual(payload["spec"]["sharedQuery"]["dimensions"], ["player_name"])
        self.assertEqual(
            payload["spec"]["sharedQuery"]["filters"],
            [{"kind": "last_n_games", "value": 10}],
        )
        self.assertEqual(
            payload["spec"]["sharedQuery"]["orders"],
            [{"kind": "desc", "metric": "total_points"}],
        )
        self.assertEqual(payload["spec"]["sharedQuery"]["linkedFilters"], [])
        self.assertEqual(payload["spec"]["sharedQuery"]["limit"], 10)
        self.assertEqual(payload["spec"]["entityFilters"], [])
        self.assertIsNone(payload["spec"]["comparison"])

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_valid_object_query_template_normalizes_to_haskell_query_json(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "object_query",
            "core_fact_object": "PlayerSeason",
            "row_object": "Player",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [
              {"kind": "exact_season", "value": "2025-26"},
              {"kind": "season_type", "value": "regular_season"}
            ],
            "orders": [{"kind": "desc", "metric": "total_points"}],
            "assumptions": []
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me players and their total points in the 2025-26 regular season"
        )

        self.assertEqual(payload["kind"], "object_query")
        self.assertEqual(payload["spec"]["rowObject"], "Player")
        self.assertEqual(payload["spec"]["sharedQuery"]["coreFactObject"], "PlayerSeason")
        self.assertEqual(
            payload["spec"]["sharedQuery"]["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(payload["spec"]["sharedQuery"]["linkedFilters"], [])
        self.assertIsNone(payload["spec"]["sharedQuery"]["limit"])

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_malformed_json_is_rejected_clearly(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = "{not valid json"

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "Show me the top 10 players by points over the last 10 games"
            )

        self.assertIn("malformed JSON", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_unsupported_values_are_rejected_clearly(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "Game",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "orders": [{"kind": "desc", "metric": "total_points"}]
          }
        }
        """

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "Show me the top 10 players by points over the last 10 games"
            )

        self.assertIn("invalid supported query template", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_omitted_optional_fields_normalize_cleanly(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["average_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}]
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me players by average points over the last 10 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        self.assertIsNone(payload["spec"]["sharedQuery"]["timeGrain"])
        self.assertEqual(payload["spec"]["sharedQuery"]["linkedFilters"], [])
        self.assertEqual(
            payload["spec"]["sharedQuery"]["orders"],
            [{"kind": "desc", "metric": "average_points"}],
        )
        self.assertIsNone(payload["spec"]["sharedQuery"]["limit"])
        self.assertEqual(payload["spec"]["sharedQuery"]["assumptions"], [])
        self.assertEqual(payload["spec"]["entityFilters"], [])
        self.assertIsNone(payload["spec"]["comparison"])

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_comparison_names_normalize_into_structured_player_refs(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "entity_filters": ["Brunson", "Tatum"],
            "comparison": {
              "kind": "compare_entities",
              "entities": ["Brunson", "Tatum"]
            },
            "assumptions": ["Interpreted 'scoring' as total points."]
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Compare Brunson and Tatum scoring over the last 10 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        self.assertEqual(len(payload["spec"]["entityFilters"]), 2)
        self.assertEqual(payload["spec"]["entityFilters"][0]["playerName"], "Jalen Brunson")
        self.assertEqual(payload["spec"]["entityFilters"][1]["playerName"], "Jayson Tatum")
        self.assertEqual(
            payload["spec"]["comparison"]["entities"][0]["playerName"], "Jalen Brunson"
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_ambiguous_player_alias_fails_clearly(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "entity_filters": ["Jalen", "Tatum"],
            "comparison": {
              "kind": "compare_entities",
              "entities": ["Jalen", "Tatum"]
            },
            "assumptions": ["Interpreted 'scoring' as total points."]
          }
        }
        """

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "Compare Jalen and Tatum scoring over the last 10 games"
            )

        self.assertIn("ambiguous", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_unknown_player_alias_fails_clearly(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "entity_filters": ["Jokic", "Tatum"],
            "comparison": {
              "kind": "compare_entities",
              "entities": ["Jokic", "Tatum"]
            },
            "assumptions": ["Interpreted 'scoring' as total points."]
          }
        }
        """

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "Compare Jokic and Tatum scoring over the last 10 games"
            )

        self.assertIn("Could not resolve player name", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_explicit_season_team_player_average_query_rejects_invalid_game_grain(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["average_points"],
            "dimensions": ["player_name"],
            "filters": [
              {"kind": "exact_season", "value": "2025-26"},
              {"kind": "season_type", "value": "regular_season"}
            ],
            "linked_filters": [
              {"target_object": "Team", "attribute": "team_name", "value": "Lakers"}
            ],
            "orders": [{"kind": "desc", "metric": "average_points"}],
            "assumptions": []
          }
        }
        """

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "Show me players by average points for the Lakers in the 2025-26 regular season"
            )

        self.assertIn("invalid supported query template", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_linked_team_filter_normalizes_into_haskell_query_json(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["average_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "linked_filters": [
              {"target_object": "Team", "attribute": "team_name", "value": "Lakers"}
            ],
            "orders": [{"kind": "desc", "metric": "average_points"}],
            "assumptions": []
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me players by average points for the Lakers over the last 10 games"
        )

        self.assertEqual(payload["kind"], "metric_query")
        self.assertEqual(payload["spec"]["sharedQuery"]["coreFactObject"], "PlayerGame")
        self.assertEqual(
            payload["spec"]["sharedQuery"]["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_limited_linked_team_object_query_normalizes_into_haskell_query_json(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "object_query",
            "core_fact_object": "PlayerGame",
            "row_object": "Player",
            "metrics": ["total_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "linked_filters": [
              {"target_object": "Team", "attribute": "team_name", "value": "Knicks"}
            ],
            "orders": [{"kind": "desc", "metric": "total_points"}],
            "limit": 5,
            "assumptions": []
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me the top 5 players and their total points for the Knicks over the last 10 games"
        )

        self.assertEqual(payload["kind"], "object_query")
        self.assertEqual(payload["spec"]["rowObject"], "Player")
        self.assertEqual(payload["spec"]["sharedQuery"]["limit"], 5)
        self.assertEqual(
            payload["spec"]["sharedQuery"]["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Knicks"}],
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_linked_team_filter_supports_player_season_team_queries(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerSeasonTeam",
            "metrics": ["average_points"],
            "dimensions": ["player_name"],
            "filters": [
              {"kind": "exact_season", "value": "2025-26"},
              {"kind": "season_type", "value": "regular_season"}
            ],
            "linked_filters": [
              {"target_object": "Team", "attribute": "team_name", "value": "Lakers"}
            ],
            "orders": [{"kind": "desc", "metric": "average_points"}],
            "assumptions": []
          }
        }
        """

        payload = interpret_question_to_planner_query(
            "Show me players by average points for the Lakers in the 2025-26 regular season"
        )

        self.assertEqual(
            payload["spec"]["sharedQuery"]["coreFactObject"], "PlayerSeasonTeam"
        )
        self.assertEqual(
            payload["spec"]["sharedQuery"]["linkedFilters"],
            [{"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}],
        )

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_unsupported_response_raises_clear_reason(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "unsupported",
          "reason": "last month trend is not supported by the current live contract"
        }
        """

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "What is the trend in points over the last month?"
            )

        self.assertIn("last month trend", str(context.exception))

    @patch("apps.cli.semantic_interpreter._call_gemini")
    def test_unsupported_linked_filter_values_are_rejected_clearly(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = """
        {
          "status": "ok",
          "query": {
            "query_kind": "metric_query",
            "core_fact_object": "PlayerGame",
            "metrics": ["average_points"],
            "dimensions": ["player_name"],
            "filters": [{"kind": "last_n_games", "value": 10}],
            "linked_filters": [
              {"target_object": "Team", "attribute": "team_abbreviation", "value": "LAL"}
            ],
            "orders": [{"kind": "desc", "metric": "average_points"}],
            "assumptions": []
          }
        }
        """

        with self.assertRaises(SemanticInterpreterError) as context:
            interpret_question_to_planner_query(
                "Show me players by average points for LAL over the last 10 games"
            )

        self.assertIn("invalid supported query template", str(context.exception))


if __name__ == "__main__":
    unittest.main()
