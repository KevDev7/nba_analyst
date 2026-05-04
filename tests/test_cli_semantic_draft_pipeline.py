from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

import duckdb

from apps.assistant.pipeline import ROOT
from apps.cli.main import run_cli
from apps.assistant.semantic.interpreter import interpret_question_to_semantic_draft
from scripts.load_gold_snapshot import load_database


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"

SAMPLE_DRAFT = {
    "task": "rank",
    "subject": "players",
    "measure": "points",
    "time_window": {"kind": "last_n_games", "value": 10},
    "limit": 10,
    "sort": "desc",
    "assumptions": [],
}


def call_plan_semantic_draft(draft: dict) -> dict:
    result = subprocess.run(
        [
            "cabal",
            "run",
            "-v0",
            "--builddir=/tmp/nba-analyst-slice36-cabal",
            "ontology-hs",
            "--",
            "plan-semantic-draft-json",
            "--ontology",
            str(ONTOLOGY_PATH),
            "--draft-json",
            json.dumps(draft),
        ],
        cwd=HASKELL_SERVICE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    payload_text = result.stdout.strip() or result.stderr.strip()
    if result.returncode != 0:
        raise AssertionError(payload_text)
    return json.loads(payload_text)


class CliSemanticDraftPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        interpret_question_to_semantic_draft.cache_clear()

    def test_haskell_plans_semantic_draft_into_current_ontology_ir(self) -> None:
        payload = call_plan_semantic_draft(SAMPLE_DRAFT)

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(shared["limit"], 10)
        self.assertEqual(payload["resolved_query"]["resolved"]["displayName"]["columnName"], "full_name")
        self.assertEqual(payload["execution_plan"]["result_shape"], "ranking")

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_interpreter_returns_semantic_draft(
        self, mock_call_gemini
    ) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": SAMPLE_DRAFT})

        draft = interpret_question_to_semantic_draft(
            "Show me the top 10 players by points over the last 10 games"
        )

        self.assertEqual(draft["task"], SAMPLE_DRAFT["task"])
        self.assertEqual(draft["subject"], SAMPLE_DRAFT["subject"])
        self.assertEqual(draft["measure"], SAMPLE_DRAFT["measure"])
        self.assertEqual(draft["time_window"], SAMPLE_DRAFT["time_window"])
        self.assertEqual(draft["limit"], SAMPLE_DRAFT["limit"])

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_runs_draft_to_haskell_to_runtime_end_to_end(self, mock_call_gemini) -> None:
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": SAMPLE_DRAFT})
        database_path = load_database()
        with duckdb.connect(str(database_path), read_only=True) as conn:
            expected_name, expected_team, expected_points = conn.execute(
                """
                WITH recent_rows AS (
                  SELECT
                    pg.person_id,
                    p.full_name,
                    t.team_abbreviation,
                    pg.game_date,
                    pg.points,
                    ROW_NUMBER() OVER (
                      PARTITION BY pg.person_id
                      ORDER BY pg.game_date DESC
                    ) AS game_rank
                  FROM player_game pg
                  JOIN player p ON pg.person_id = p.person_id
                  LEFT JOIN team t ON pg.team_id = t.team_id
                )
                SELECT full_name, team_abbreviation, SUM(points) AS metric_value
                FROM recent_rows
                WHERE game_rank <= 10
                GROUP BY person_id, full_name, team_abbreviation
                ORDER BY metric_value DESC, full_name ASC
                LIMIT 1
                """
            ).fetchone()

        output = run_cli("Show me the top 10 players by points over the last 10 games")

        self.assertIn("Top 10 players by total points over the last 10 games", output)
        self.assertIn("Rank | Player | Team | Games Played | Minutes | Date Range | Total Points", output)
        self.assertIn(
            f"1 | {expected_name} | {expected_team} |",
            output,
        )
        self.assertIn(f"| {int(expected_points)}", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_rank_wording_variation_uses_ontology_grounding(self, mock_call_gemini) -> None:
        varied_draft = {
            **SAMPLE_DRAFT,
            "subject": "nba players",
            "limit": 7,
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": varied_draft})

        output = run_cli("What are the top 7 nba players by points these last ten games")

        self.assertIn("Top 7 players by total points over the last 10 games", output)
        self.assertIn("Rank | Player | Team | Games Played | Minutes | Date Range | Total Points", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_best_defensive_rating_uses_best_wording_after_ascending_grounding(self, mock_call_gemini) -> None:
        best_defense_draft = {
            "task": "rank",
            "subject": "teams",
            "measure": "defensive rating",
            "measures": ["defensive rating"],
            "filters": [
                {"field": "season", "op": "=", "value": "2025-26"},
                {"field": "season type", "op": "=", "value": "regular season"},
            ],
            "time_window": {"kind": "season", "value": "2025-26"},
            "limit": 10,
            "sort": None,
            "rank_intent": "best",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": best_defense_draft})

        output = run_cli("Who are the best defensive teams this season?")

        self.assertIn("Best 10 teams by defensive rating in the 2025-26 regular season", output)
        self.assertNotIn("Bottom 10 teams by defensive rating", output)
        self.assertIn("Rank | Team | Abbrev | Season | Season Type | Games Played | Defensive Rating", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_worst_defensive_rating_uses_worst_wording_after_descending_grounding(self, mock_call_gemini) -> None:
        worst_defense_draft = {
            "task": "rank",
            "subject": "teams",
            "measure": "defensive rating",
            "measures": ["defensive rating"],
            "filters": [
                {"field": "season", "op": "=", "value": "2025-26"},
                {"field": "season type", "op": "=", "value": "regular season"},
            ],
            "time_window": {"kind": "season", "value": "2025-26"},
            "limit": 10,
            "sort": None,
            "rank_intent": "worst",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": worst_defense_draft})

        output = run_cli("Who are the worst defensive teams this season?")

        self.assertIn("Worst 10 teams by defensive rating in the 2025-26 regular season", output)
        self.assertNotIn("Top 10 teams by defensive rating", output)
        self.assertIn("Rank | Team | Abbrev | Season | Season Type | Games Played | Defensive Rating", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_fewest_turnovers_uses_quantity_intent_wording(self, mock_call_gemini) -> None:
        fewest_turnovers_draft = {
            "task": "rank",
            "subject": "players",
            "measure": "turnovers",
            "measures": ["turnovers"],
            "time_window": {"kind": "last_n_games", "value": 10},
            "limit": 10,
            "sort": None,
            "rank_intent": "fewest",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": fewest_turnovers_draft})

        output = run_cli("Which players have the fewest turnovers over the last 10 games?")

        self.assertIn("Fewest 10 players by total turnovers over the last 10 games", output)
        self.assertNotIn("Bottom 10 players by total turnovers", output)
        self.assertIn("Rank | Player | Team | Games Played | Minutes | Date Range | Total Turnovers", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_stat_feed_plural_steals_label_grounds_end_to_end(self, mock_call_gemini) -> None:
        stls_draft = {
            "task": "rank",
            "subject": "players",
            "measure": "stls",
            "measures": ["stls"],
            "time_window": {"kind": "last_n_games", "value": 10},
            "limit": 10,
            "sort": "desc",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": stls_draft})

        output = run_cli("Who leads the league in stls over the last 10 games?")

        self.assertIn("Top 10 players by total steals over the last 10 games", output)
        self.assertIn("Rank | Player | Team | Games Played | Minutes | Date Range | Total Steals", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_team_plus_minus_pasted_label_grounds_to_point_differential(self, mock_call_gemini) -> None:
        plus_minus_draft = {
            "task": "rank",
            "subject": "teams",
            "measure": "PLUS_MINUS",
            "measures": ["PLUS_MINUS"],
            "time_window": {"kind": "last_n_games", "value": 10},
            "limit": 10,
            "sort": "desc",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": plus_minus_draft})

        output = run_cli("Rank teams by PLUS_MINUS over the last 10 games")

        self.assertIn("Top 10 teams by total point differential over the last 10 games", output)
        self.assertIn("Rank | Team | Abbrev | Games Played | Date Range | Total Point Differential", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_win_percentage_pasted_label_grounds_end_to_end(self, mock_call_gemini) -> None:
        win_pct_draft = {
            "task": "rank",
            "subject": "teams",
            "measure": "W_PCT",
            "measures": ["W_PCT"],
            "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
            "time_window": {"kind": "season", "value": "2025-26"},
            "limit": 10,
            "sort": "desc",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": win_pct_draft})

        output = run_cli("Rank teams by W_PCT this season")

        self.assertIn("Top 10 teams by win percentage in the 2025-26 regular season", output)
        self.assertIn("Rank | Team | Abbrev | Season | Season Type | Games Played | Win Percentage", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_bench_scorers_phrase_reaches_starter_value_filter(self, mock_call_gemini) -> None:
        bench_scorers_draft = {
            "task": "rank",
            "subject": "players",
            "measure": "scoring",
            "measures": ["scoring"],
            "dimensions": [],
            "filters": [{"field": "is starter", "op": "=", "value": "bench"}],
            "time_window": {"kind": "last_n_games", "value": 10},
            "grain": None,
            "order": [{"by": "scoring", "direction": "desc"}],
            "limit": None,
            "sort": None,
            "rank_intent": "top",
            "entities": [],
            "operations": [],
            "assumptions": ["Interpreted 'scorers' as players ranked by points."],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": bench_scorers_draft})

        output = run_cli("Who are the top bench scorers over the last 10 games?")

        self.assertIn("where is starter equals false over the last 10 games", output)
        self.assertIn("Rank | Player | Team | Games Played | Minutes | Date Range | Total Points", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_road_team_phrase_reaches_home_away_value_filter(self, mock_call_gemini) -> None:
        road_team_draft = {
            "task": "rank",
            "subject": "teams",
            "measure": "net rating",
            "measures": ["net rating"],
            "dimensions": [],
            "filters": [{"field": "team home or away", "op": "=", "value": "road"}],
            "time_window": {"kind": "last_n_games", "value": 10},
            "grain": None,
            "order": [{"by": "net rating", "direction": "desc"}],
            "limit": None,
            "sort": None,
            "rank_intent": "ranked",
            "entities": [],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": road_team_draft})

        output = run_cli("Rank teams by net rating on the road over the last 10 games")

        self.assertIn("where team home or away equals away over the last 10 games", output)
        self.assertIn("Rank | Team | Abbrev | Games Played | Date Range | Average Net Rating", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_eastern_conference_phrase_reaches_conference_value_filter(self, mock_call_gemini) -> None:
        east_defense_draft = {
            "task": "rank",
            "subject": "teams",
            "measure": "defensive rating",
            "measures": ["defensive rating"],
            "dimensions": [],
            "filters": [{"field": "conference", "op": "=", "value": "east"}],
            "time_window": {"kind": "season", "value": None},
            "grain": None,
            "order": [],
            "limit": None,
            "sort": None,
            "rank_intent": "best",
            "entities": [],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": east_defense_draft})

        output = run_cli("Best Eastern Conference teams by defensive rating this season")

        self.assertIn("Ranked best to worst teams by defensive rating where conference equals east", output)
        self.assertIn("in the 2025-26 regular season", output)
        self.assertIn("Rank | Team | Abbrev | Season | Season Type | Games Played | Defensive Rating", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_postseason_phrase_reaches_season_type_value_filter(self, mock_call_gemini) -> None:
        postseason_draft = {
            "task": "rank",
            "subject": "players",
            "measure": "points",
            "measures": ["points"],
            "dimensions": [],
            "filters": [{"field": "season type", "op": "=", "value": "playoffs"}],
            "time_window": {"kind": "season", "value": "2024-25"},
            "grain": None,
            "order": [{"by": "points", "direction": "desc"}],
            "limit": None,
            "sort": None,
            "rank_intent": "top",
            "entities": [],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": postseason_draft})

        output = run_cli("Top players by points in the 2024-25 postseason")

        self.assertIn("Ranked players by total points in the 2024-25 playoffs", output)
        self.assertIn("Rank | Player | Season | Season Type | Games Played | Total Points", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_rank_season_draft_reaches_existing_season_surface(self, mock_call_gemini) -> None:
        season_draft = {
            "task": "rank",
            "subject": "players",
            "measure": "average points",
            "time_window": {"kind": "season", "value": "2025-26"},
            "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
            "limit": 10,
            "sort": "desc",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": season_draft})

        output = run_cli("Show me players by average points in the 2025-26 regular season")

        self.assertIn("Top 10 players by average points in the 2025-26 regular season", output)
        self.assertIn("Rank | Player | Season | Season Type | Games Played | Average Points", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_object_draft_runs_to_object_rows_answer(self, mock_call_gemini) -> None:
        object_draft = {
            "task": "object",
            "subject": "players",
            "measure": "total points",
            "measures": ["total points"],
            "dimensions": [],
            "filters": [],
            "time_window": {"kind": "last_n_games", "value": 10},
            "grain": None,
            "order": [],
            "limit": None,
            "sort": "desc",
            "entities": [],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": object_draft})

        output = run_cli("Show me players and their total points over the last 10 games")

        self.assertIn("Interpreted as: Players and their total points over the last 10 games.", output)
        self.assertIn("Players ordered by total points over the last 10 games", output)
        self.assertIn("Player | Team | Games Played | Minutes | Date Range | Total Points", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_trend_draft_runs_to_time_series_answer(self, mock_call_gemini) -> None:
        trend_draft = {
            "task": "trend",
            "subject": "teams",
            "measure": "average points",
            "dimensions": ["team"],
            "filters": [],
            "time_window": {"kind": "past_year", "value": None},
            "grain": "month",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": trend_draft})

        output = run_cli("What are the monthly average points by team over the past year?")

        self.assertIn("Monthly average points by team over the past year are shown below.", output)
        self.assertIn("Month | Team | Average Points", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_weekly_trend_uses_calendar_week_bucket(self, mock_call_gemini) -> None:
        trend_draft = {
            "task": "trend",
            "subject": "teams",
            "measure": "average points",
            "dimensions": ["team"],
            "filters": [],
            "time_window": {"kind": "past_year", "value": None},
            "grain": "week",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": trend_draft})

        output = run_cli("Show weekly average points by team over the past year")

        self.assertIn("Weekly average points by team over the past year are shown below.", output)
        self.assertIn("Week | Team | Average Points", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_month_over_month_trend_uses_calendar_month_bucket(self, mock_call_gemini) -> None:
        trend_draft = {
            "task": "trend",
            "subject": "teams",
            "measure": "net rating",
            "measures": ["net rating"],
            "dimensions": ["team"],
            "filters": [],
            "time_window": {"kind": "past_year", "value": None},
            "grain": "month",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": trend_draft})

        output = run_cli("Show month over month team net rating over the past year")

        self.assertIn("Average net rating by team by month over the past year.", output)
        self.assertIn("Monthly average net rating by team over the past year are shown below.", output)
        self.assertIn("Month | Team | Average Net Rating", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_season_by_season_trend_uses_season_bucket_without_current_season_default(self, mock_call_gemini) -> None:
        trend_draft = {
            "task": "trend",
            "subject": "teams",
            "measure": "wins",
            "measures": ["wins"],
            "dimensions": ["team"],
            "filters": [],
            "time_window": {"kind": "all", "value": None},
            "grain": "season",
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": trend_draft})

        output = run_cli("Show season by season team wins")

        self.assertIn("Wins by team by season.", output)
        self.assertIn("Season-by-season wins by team are shown below.", output)
        self.assertNotIn("Assumed season year is 2025-26", output)
        self.assertIn("Season | Team | Wins", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_game_by_game_player_log_uses_find_rows_with_opponent_display(self, mock_call_gemini) -> None:
        game_log_draft = {
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
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": game_log_draft})

        output = run_cli("Show Jalen Brunson game by game points over his last 10 games")

        self.assertIn("Matching players are shown below.", output)
        self.assertIn(
            "Interpreted as: Players where full name equals Jalen Brunson over the last 10 games sorted by game date descending.",
            output,
        )
        self.assertIn("Game Date | Team Name | Opponent | Points | Full Name", output)
        self.assertIn("Jalen Brunson", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_month_by_month_comparison_uses_calendar_month_bucket(self, mock_call_gemini) -> None:
        compare_draft = {
            "task": "compare",
            "subject": "teams",
            "measure": "points",
            "measures": ["points"],
            "dimensions": [],
            "filters": [],
            "time_window": {"kind": "past_year", "value": None},
            "grain": "month",
            "entities": ["Lakers", "Warriors"],
            "operations": [],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": compare_draft})

        output = run_cli("Compare Lakers and Warriors by points month by month over the past year")

        self.assertIn("compared by total points by month over the past year.", output)
        self.assertIn("Total points comparison by month over the past year is shown below.", output)
        self.assertIn("Month | Team | Abbrev | Games | Total Points", output)

    @patch("apps.assistant.semantic.interpreter._call_gemini")
    def test_cli_compare_resolves_entities_and_runs_multi_step_plan(self, mock_call_gemini) -> None:
        compare_draft = {
            "task": "compare",
            "subject": "players",
            "measure": "points",
            "time_window": {"kind": "last_n_games", "value": 10},
            "entities": ["Brunson", "Tatum"],
            "assumptions": [],
        }
        mock_call_gemini.return_value = json.dumps({"status": "ok", "draft": compare_draft})

        output = run_cli("Compare Brunson and Tatum scoring over the last 10 games")

        self.assertIn("led in total points over the last 10 games", output)
        self.assertIn("Comparison", output)
        self.assertIn("Jalen Brunson", output)
        self.assertIn("Jayson Tatum", output)


if __name__ == "__main__":
    unittest.main()
