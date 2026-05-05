from __future__ import annotations

import unittest

from apps.assistant.pipeline import call_haskell_planner_for_semantic_draft
from tests.planner_helpers import call_plan_query_json


def metric_shared(**overrides: object) -> dict[str, object]:
    shared: dict[str, object] = {
        "coreFactObject": "PlayerGame",
        "metrics": ["average_points"],
        "dimensions": ["full_name"],
        "timeGrain": None,
        "filters": [{"kind": "last_n_games", "value": 10}],
        "orders": [{"kind": "desc", "metric": "average_points"}],
        "limit": 5,
        "assumptions": [],
    }
    shared.update(overrides)
    return shared


class RowPredicateMigrationTests(unittest.TestCase):
    def test_semantic_rank_draft_lowers_predicate_to_shared_row_predicate(self) -> None:
        payload = call_haskell_planner_for_semantic_draft(
            {
                "task": "rank",
                "subject": "players",
                "measure": "average points",
                "measures": ["average points"],
                "dimensions": [],
                "filters": [],
                "predicate": {
                    "kind": "and",
                    "predicates": [
                        {"kind": "leaf", "field": "team", "op": "in", "value": ["Lakers", "Warriors"]},
                        {"kind": "leaf", "field": "minutes", "op": "between", "value": {"lower": 20, "upper": 30}},
                    ],
                },
                "time_window": {"kind": "last_n_games", "value": 10},
                "grain": None,
                "order": [{"by": "average points", "direction": "desc"}],
                "limit": 5,
                "sort": "desc",
                "entities": [],
                "operations": [],
                "assumptions": [],
            }
        )

        row_predicate = payload["query"]["spec"]["sharedQuery"]["rowPredicate"]
        sql = payload["execution_plan"]["execution"]["steps"][0]["sql"]

        self.assertEqual(row_predicate["kind"], "and")
        self.assertEqual(row_predicate["predicates"][0]["field"]["attribute"], "team_name")
        self.assertEqual(row_predicate["predicates"][1]["field"]["attribute"], "minutes_played")
        self.assertIn("lf1.team_name IN ('Lakers', 'Warriors')", sql)
        self.assertIn("f.minutes_played BETWEEN 20 AND 30", sql)

    def test_rank_uses_shared_row_predicate_tree(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": metric_shared(
                    rowPredicate={
                        "kind": "or",
                        "predicates": [
                            {
                                "kind": "leaf",
                                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                                "operator": "in",
                                "value": {"kind": "list", "values": ["Lakers", "Warriors"]},
                            },
                            {
                                "kind": "leaf",
                                "field": {"targetObject": "PlayerGame", "attribute": "minutes_played", "location": "row"},
                                "operator": "between",
                                "value": {"kind": "range", "lower": 20, "upper": 30},
                            },
                        ],
                    }
                ),
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        sql = planner_output["execution_plan"]["execution"]["steps"][0]["sql"]

        self.assertEqual(planner_output["execution_plan"]["answer_context"]["predicates"]["row"]["kind"], "or")
        self.assertIn("lf1.team_name IN ('Lakers', 'Warriors')", sql)
        self.assertIn("f.minutes_played BETWEEN 20 AND 30", sql)

    def test_object_uses_shared_row_predicate_tree(self) -> None:
        payload = {
            "kind": "object_query",
            "spec": {
                "rowObject": "Player",
                "sharedQuery": metric_shared(
                    metrics=["total_points"],
                    orders=[{"kind": "desc", "metric": "total_points"}],
                    rowPredicate={
                        "kind": "not",
                        "predicate": {
                            "kind": "leaf",
                            "field": {"targetObject": "Team", "attribute": "conference", "location": "row"},
                            "operator": "equals",
                            "value": {"kind": "scalar", "value": "Western"},
                        },
                    },
                ),
            },
        }

        planner_output = call_plan_query_json(payload)
        sql = planner_output["execution_plan"]["execution"]["steps"][0]["sql"]

        self.assertEqual(planner_output["execution_plan"]["answer_context"]["predicates"]["row"]["predicate"]["value"]["value"], "west")
        self.assertIn("NOT (lf1.conference = 'west')", sql)

    def test_aggregate_uses_shared_row_predicate_tree(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": metric_shared(
                    coreFactObject="TeamGame",
                    metrics=["average_points"],
                    dimensions=["team_name"],
                    orders=[],
                    rowPredicate={
                        "kind": "leaf",
                        "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                        "operator": "contains",
                        "value": {"kind": "scalar", "value": "War"},
                    },
                ),
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        sql = planner_output["execution_plan"]["execution"]["steps"][0]["sql"]

        self.assertEqual(planner_output["execution_plan"]["answer_context"]["result_shape"], "aggregate")
        self.assertIn("lf1.team_name ILIKE '%War%'", sql)

    def test_trend_uses_shared_row_predicate_tree(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": metric_shared(
                    coreFactObject="TeamGame",
                    metrics=["average_points"],
                    dimensions=["team_name"],
                    timeGrain="month",
                    filters=[{"kind": "past_year"}],
                    orders=[],
                    limit=None,
                    rowPredicate={
                        "kind": "leaf",
                        "field": {"targetObject": "Team", "attribute": "conference", "location": "row"},
                        "operator": "not_equals",
                        "value": {"kind": "scalar", "value": "Western"},
                    },
                ),
                "entityFilters": [],
                "comparison": None,
            },
        }

        planner_output = call_plan_query_json(payload)
        sql = planner_output["execution_plan"]["execution"]["steps"][0]["sql"]

        self.assertEqual(planner_output["execution_plan"]["answer_context"]["result_shape"], "time_series")
        self.assertIn("lf1.conference <> 'west'", sql)

    def test_compare_uses_shared_row_predicate_tree(self) -> None:
        payload = {
            "kind": "metric_query",
            "spec": {
                "sharedQuery": metric_shared(
                    metrics=["total_points"],
                    orders=[],
                    limit=None,
                    rowPredicate={
                        "kind": "leaf",
                        "field": {"targetObject": "Team", "attribute": "conference", "location": "row"},
                        "operator": "equals",
                        "value": {"kind": "scalar", "value": "Eastern"},
                    },
                ),
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
        sql = planner_output["execution_plan"]["execution"]["steps"][0]["sql"]

        self.assertEqual(planner_output["execution_plan"]["answer_context"]["result_shape"], "comparison")
        self.assertIn("lf1.conference = 'east'", sql)


if __name__ == "__main__":
    unittest.main()
