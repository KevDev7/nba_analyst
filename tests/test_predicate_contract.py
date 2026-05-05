from __future__ import annotations

import unittest

from tests.planner_helpers import call_plan_query_json


def metric_query_payload(**shared_overrides: object) -> dict[str, object]:
    shared_query: dict[str, object] = {
        "coreFactObject": "PlayerGame",
        "metrics": ["average_points"],
        "dimensions": ["full_name"],
        "timeGrain": None,
        "filters": [{"kind": "last_n_games", "value": 10}],
        "orders": [{"kind": "desc", "metric": "average_points"}],
        "limit": 5,
        "assumptions": [],
    }
    shared_query.update(shared_overrides)
    return {
        "kind": "metric_query",
        "spec": {
            "sharedQuery": shared_query,
            "entityFilters": [],
            "comparison": None,
        },
    }


class PredicateContractTests(unittest.TestCase):
    def test_existing_flat_filter_contract_still_plans(self) -> None:
        planner_output = call_plan_query_json(metric_query_payload())
        shared = planner_output["query"]["spec"]["sharedQuery"]

        self.assertEqual(shared["filters"], [{"kind": "last_n_games", "value": 10}])
        self.assertEqual(shared["rowPredicate"], None)
        self.assertEqual(shared["resultPredicate"], None)
        self.assertEqual(planner_output["execution_plan"]["answer_context"]["result_shape"], "ranking")

    def test_row_predicate_tree_executes_for_metric_queries(self) -> None:
        payload = metric_query_payload(
            rowPredicate={
                "kind": "or",
                "predicates": [
                    {
                        "kind": "leaf",
                        "field": {
                            "targetObject": "Team",
                            "attribute": "team_name",
                            "location": "row",
                        },
                        "operator": "in",
                        "value": {"kind": "list", "values": ["Lakers", "Warriors"]},
                    },
                    {
                        "kind": "leaf",
                        "field": {
                            "targetObject": "PlayerGame",
                            "attribute": "minutes_played",
                            "location": "row",
                        },
                        "operator": "between",
                        "value": {"kind": "range", "lower": 20, "upper": 30},
                    },
                ],
            }
        )

        planner_output = call_plan_query_json(payload)
        execution_plan = planner_output["execution_plan"]
        sql = execution_plan["execution"]["steps"][0]["sql"]

        self.assertEqual(execution_plan["answer_context"]["predicates"]["row"]["kind"], "or")
        self.assertIn("lf1.team_name IN ('Lakers', 'Warriors')", sql)
        self.assertIn("f.minutes_played BETWEEN 20 AND 30", sql)

    def test_result_predicate_tree_executes_for_metric_queries(self) -> None:
        payload = metric_query_payload(
            resultPredicate={
                "kind": "or",
                "predicates": [
                    {
                        "kind": "leaf",
                        "field": {
                            "targetObject": "PlayerGame",
                            "attribute": "average_points",
                            "location": "result",
                        },
                        "operator": "between",
                        "value": {"kind": "range", "lower": 20, "upper": 30},
                    },
                    {
                        "kind": "leaf",
                        "field": {
                            "targetObject": "PlayerGame",
                            "attribute": "average_minutes",
                            "location": "result",
                        },
                        "operator": "greater_than",
                        "value": {"kind": "scalar", "value": 32},
                    },
                ],
            }
        )

        planner_output = call_plan_query_json(payload)
        execution_plan = planner_output["execution_plan"]
        sql = execution_plan["execution"]["steps"][0]["sql"]

        self.assertEqual(execution_plan["answer_context"]["predicates"]["result"]["kind"], "or")
        self.assertIn("ROUND(AVG(__result_predicate_1_source), 1) AS result_predicate_1", sql)
        self.assertIn("(metric_value BETWEEN 20 AND 30 OR result_predicate_1 > 32)", sql)

    def test_result_predicate_rejects_row_fields(self) -> None:
        payload = metric_query_payload(
            resultPredicate={
                "kind": "leaf",
                "field": {
                    "targetObject": "PlayerGame",
                    "attribute": "minutes_played",
                    "location": "row",
                },
                "operator": "greater_than",
                "value": {"kind": "scalar", "value": 30},
            }
        )

        with self.assertRaises(RuntimeError) as context:
            call_plan_query_json(payload)

        self.assertIn("Result predicate trees only support result-level predicate fields", str(context.exception))

    def test_find_predicate_tree_executes_for_find_queries(self) -> None:
        payload = {
            "kind": "find_query",
            "spec": {
                "findCoreFactObject": "Team",
                "findTargetObject": "Team",
                "findDisplayDimensions": ["team_name"],
                "findPredicateTree": {
                    "kind": "not",
                    "predicate": {
                        "kind": "leaf",
                        "field": {
                            "targetObject": "Team",
                            "attribute": "team_name",
                            "location": "row",
                        },
                        "operator": "contains",
                        "value": {"kind": "scalar", "value": "Lakers"},
                    },
                },
                "findFilters": [],
                "findLimit": 5,
                "findAssumptions": [],
            },
        }

        planner_output = call_plan_query_json(payload)
        execution_plan = planner_output["execution_plan"]
        sql = execution_plan["execution"]["steps"][0]["sql"]

        self.assertEqual(execution_plan["answer_context"]["result_shape"], "find_rows")
        self.assertEqual(
            execution_plan["answer_context"]["find"]["predicate_tree"]["predicate"]["operator"],
            "contains",
        )
        self.assertIn("NOT (f.team_name ILIKE '%Lakers%'", sql)


if __name__ == "__main__":
    unittest.main()
