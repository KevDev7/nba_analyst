from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


class LinkedFilterGenericGroundingTests(unittest.TestCase):
    def test_recent_metric_query_with_team_conference_linked_filter_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "conference", "value": "Western"}
                    ],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["targetObjectName"], "Team")
        self.assertEqual(resolved_filter["filterColumn"], "conference")
        self.assertEqual(resolved_filter["filterValue"], "west")
        self.assertIn("lf1.conference = 'west'", planner_output["execution_plan"]["steps"][0]["sql"])

    def test_mixed_case_conference_alias_canonicalizes(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "conference", "value": "eAst"}
                    ],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["filterValue"], "east")

    def test_recent_object_query_with_team_division_linked_filter_succeeds(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "division", "value": "Pacific"}
                    ],
                    "orders": [{"kind": "desc", "metric": "total_points"}],
                    "limit": 5,
                    "assumptions": [],
                },
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["filterColumn"], "division")
        self.assertEqual(resolved_filter["filterValue"], "Pacific")

    def test_season_metric_query_with_team_abbreviation_linked_filter_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerSeasonTeam",
                    "metrics": ["points_per_game"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [
                        {"kind": "exact_season", "value": "2025-26"},
                        {"kind": "season_type", "value": "regular_season"},
                    ],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_abbreviation", "value": "LAL"}
                    ],
                    "orders": [{"kind": "desc", "metric": "points_per_game"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["filterColumn"], "team_abbreviation")
        self.assertEqual(resolved_filter["filterValue"], "LAL")

    def test_team_name_linked_filter_works(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "Lakers"}
                    ],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["filterColumn"], "team_name")
        self.assertEqual(resolved_filter["filterValue"], "Lakers")

    def test_non_team_target_player_full_name_now_succeeds(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Player", "attribute": "full_name", "value": "sample"}
                    ],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["targetObjectName"], "Player")
        self.assertEqual(resolved_filter["filterColumn"], "full_name")

    def test_more_than_one_linked_filter_is_grounded(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "conference", "value": "Western"},
                        {"targetObject": "Team", "attribute": "division", "value": "Pacific"},
                    ],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filters = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"]

        self.assertEqual(
            [(filter_value["filterColumn"], filter_value["filterValue"]) for filter_value in resolved_filters],
            [("conference", "west"), ("division", "Pacific")],
        )

    def test_trend_accepts_ontology_grounded_linked_filters(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "TeamGame",
                    "metrics": ["average_points"],
                    "dimensions": ["team_name"],
                    "timeGrain": "month",
                    "filters": [{"kind": "past_year"}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "conference", "value": "Western"}
                    ],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filters = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"]

        self.assertEqual(resolved_filters[0]["filterColumn"], "conference")
        self.assertEqual(resolved_filters[0]["filterValue"], "west")
        self.assertIn("JOIN team", planner_output["execution_plan"]["steps"][0]["sql"])
        self.assertIn("lf1.conference = 'west'", planner_output["execution_plan"]["steps"][0]["sql"])

    def test_comparison_accepts_ontology_grounded_linked_filters(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["total_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "conference", "value": "Western"}
                    ],
                    "orders": [],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": {
                    "kind": "compare_entities",
                    "targetObject": "Player",
                    "entities": [
                        {"entityId": 1628973, "entityName": "Jalen Brunson"},
                        {"entityId": 1628369, "entityName": "Jayson Tatum"},
                    ],
                },
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filters = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"]

        self.assertEqual(resolved_filters[0]["filterColumn"], "conference")
        self.assertEqual(resolved_filters[0]["filterValue"], "west")
        self.assertIn("JOIN team", planner_output["execution_plan"]["steps"][0]["sql"])

    def test_team_name_alias_canonicalizes_for_linked_filter(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": {
                    "coreFactObject": "PlayerGame",
                    "metrics": ["average_points"],
                    "dimensions": ["full_name"],
                    "timeGrain": None,
                    "filters": [{"kind": "last_n_games", "value": 10}],
                    "linkedFilters": [
                        {"targetObject": "Team", "attribute": "team_name", "value": "LA Lakers"}
                    ],
                    "orders": [{"kind": "desc", "metric": "average_points"}],
                    "limit": None,
                    "assumptions": [],
                },
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        resolved_filter = planner_output["resolved_query"]["resolved"]["linkedFiltersResolved"][0]

        self.assertEqual(resolved_filter["filterValue"], "Lakers")
        self.assertIn("lf1.team_name = 'Lakers'", planner_output["execution_plan"]["steps"][0]["sql"])

if __name__ == "__main__":
    unittest.main()
