from __future__ import annotations

import json
import subprocess
import unittest

from apps.cli.main import ROOT


HASKELL_SERVICE_DIR = ROOT / "services" / "ontology-hs"
ONTOLOGY_PATH = ROOT / "fixtures" / "ontology" / "semantic-gold.yaml"


def call_plan_semantic_draft(draft: dict) -> dict:
    result = subprocess.run(
        [
            "cabal",
            "run",
            "-v0",
            "--builddir=/tmp/nba-analyst-slice37a-cabal",
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
    payload = json.loads(payload_text)
    if result.returncode != 0:
        raise AssertionError(payload)
    return payload


class SemanticDraftGroundingTests(unittest.TestCase):
    def test_haskell_grounds_player_average_points_ranking_from_ontology(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "average_points"}])

    def test_haskell_grounds_team_points_ranking_from_ontology(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "teams",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 5,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["orders"], [{"kind": "desc", "metric": "total_points"}])
        self.assertEqual(payload["execution_plan"]["entity_label_plural"], "Teams")

    def test_haskell_rejects_unsupported_time_window_after_python_shape_validation(self) -> None:
        result = subprocess.run(
            [
                "cabal",
                "run",
                "-v0",
                "--builddir=/tmp/nba-analyst-slice37a-cabal",
                "ontology-hs",
                "--",
                "plan-semantic-draft-json",
                "--ontology",
                str(ONTOLOGY_PATH),
                "--draft-json",
                json.dumps(
                    {
                        "task": "rank",
                        "subject": "players",
                        "measure": "points",
                        "time_window": {"kind": "last_month", "value": 1},
                        "limit": 10,
                        "sort": "desc",
                        "assumptions": [],
                    }
                ),
            ],
            cwd=HASKELL_SERVICE_DIR,
            capture_output=True,
            text=True,
            check=False,
        )

        payload = json.loads(result.stdout.strip() or result.stderr.strip())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(payload["stage"], "QueryModel.SemanticDraft")
        self.assertIn("Could not ground ranking time window", payload["message"])

    def test_haskell_grounds_nba_player_wording_and_arbitrary_rank_limit(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "nba players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 7,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["limit"], 7)
        self.assertEqual(payload["execution_plan"]["limit"], 7)

    def test_haskell_grounds_bottom_rank_sort_without_desc_only_gate(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "limit": 6,
                "sort": "asc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(shared["orders"], [{"kind": "asc", "metric": "total_points"}])
        self.assertIn("ORDER BY metric_value ASC, entity_name ASC", sql)

    def test_haskell_grounds_season_rank_draft_through_ontology_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "time_window": {"kind": "season", "value": "2025-26"},
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "limit": 10,
                "sort": "desc",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "PlayerSeason")
        self.assertEqual(shared["metrics"], ["points_per_game"])
        self.assertEqual(
            shared["filters"],
            [
                {"kind": "exact_season", "value": "2025-26"},
                {"kind": "season_type", "value": "regular_season"},
            ],
        )
        self.assertEqual(payload["resolved_query"]["resolved"]["factTableName"], "player_season")

    def test_haskell_grounds_monthly_team_trend_from_ontology(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "average points",
                "dimensions": ["team"],
                "time_window": {"kind": "past_year", "value": None},
                "grain": "month",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["metrics"], ["average_points"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["timeGrain"], "month")
        self.assertEqual(shared["filters"], [{"kind": "past_year"}])
        self.assertEqual(payload["execution_plan"]["result_shape"], "time_series")

    def test_haskell_grounds_weekly_team_trend_from_same_date_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "average points",
                "dimensions": ["team"],
                "time_window": {"kind": "past_year", "value": None},
                "grain": "week",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        resolved = payload["resolved_query"]["resolved"]
        self.assertEqual(shared["coreFactObject"], "TeamGame")
        self.assertEqual(shared["timeGrain"], "week")
        self.assertIn("DATE_TRUNC('week'", resolved["timeBucketExpression"])
        self.assertEqual(payload["execution_plan"]["time_grain"], "week")

    def test_haskell_grounds_season_team_trend_through_season_surface(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "trend",
                "subject": "teams",
                "measure": "wins",
                "dimensions": ["team"],
                "filters": [{"field": "season type", "op": "=", "value": "regular season"}],
                "time_window": {"kind": "all", "value": None},
                "grain": "season",
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        self.assertEqual(shared["coreFactObject"], "TeamSeason")
        self.assertEqual(shared["metrics"], ["wins"])
        self.assertEqual(shared["dimensions"], ["team_name"])
        self.assertEqual(shared["timeGrain"], "season")
        self.assertEqual(shared["filters"], [{"kind": "season_type", "value": "regular_season"}])
        self.assertEqual(payload["resolved_query"]["resolved"]["factTableName"], "team_season")

    def test_haskell_grounds_player_comparison_from_resolved_entities(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "compare",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "entities": ["Brunson", "Tatum"],
                "resolved_entities": [
                    {"entityId": 1628973, "entityName": "Jalen Brunson"},
                    {"entityId": 1628369, "entityName": "Jayson Tatum"},
                ],
                "assumptions": [],
            }
        )

        shared = payload["query"]["spec"]["sharedQuery"]
        comparison = payload["query"]["spec"]["comparison"]
        self.assertEqual(shared["coreFactObject"], "PlayerGame")
        self.assertEqual(shared["metrics"], ["total_points"])
        self.assertEqual(shared["dimensions"], ["full_name"])
        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(comparison["targetObject"], "Player")
        self.assertEqual(payload["execution_plan"]["result_shape"], "comparison")
        self.assertEqual(payload["execution_plan"]["plan_type"], "multi_step")

    def test_haskell_grounds_multi_entity_comparison_without_two_entity_gate(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "compare",
                "subject": "players",
                "measure": "points",
                "time_window": {"kind": "last_n_games", "value": 10},
                "entities": ["Brunson", "Tatum", "Haliburton"],
                "resolved_entities": [
                    {"entityId": 1628973, "entityName": "Jalen Brunson"},
                    {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    {"entityId": 1630169, "entityName": "Tyrese Haliburton"},
                ],
                "assumptions": [],
            }
        )

        comparison = payload["query"]["spec"]["comparison"]
        sql = payload["execution_plan"]["steps"][0]["sql"]
        self.assertEqual(len(comparison["entities"]), 3)
        self.assertIn("1628973", sql)
        self.assertIn("1630169", sql)

    def test_haskell_grounds_find_family_from_semantic_draft(self) -> None:
        payload = call_plan_semantic_draft(
            {
                "task": "find",
                "subject": "teams",
                "measure": None,
                "measures": [],
                "dimensions": [],
                "filters": [{"field": "conference", "op": "=", "value": "Western"}],
                "time_window": {"kind": "all", "value": None},
                "grain": None,
                "order": [],
                "limit": 3,
                "sort": None,
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        self.assertEqual(payload["query"]["kind"], "find_query")
        self.assertEqual(payload["query"]["spec"]["findCoreFactObject"], "Team")
        self.assertEqual(payload["execution_plan"]["result_shape"], "find_rows")


if __name__ == "__main__":
    unittest.main()
