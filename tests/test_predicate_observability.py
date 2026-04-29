from __future__ import annotations

import unittest

from apps.assistant.predicate_observability import build_predicate_trace


class PredicateObservabilityTests(unittest.TestCase):
    def test_metric_predicate_trace_shows_draft_ir_resolved_plan_and_sql(self) -> None:
        semantic_draft = {
            "task": "rank",
            "filters": [{"field": "team", "op": "=", "value": "Lakers"}],
            "predicate": None,
            "result_filters": [],
            "result_predicate": {
                "kind": "leaf",
                "field": "average minutes",
                "op": ">",
                "value": 30,
            },
        }
        planner_output = {
            "query": {
                "kind": "metric_query",
                "spec": {
                    "sharedQuery": {
                        "filters": [{"kind": "last_n_games", "value": 10}],
                        "rowPredicate": {
                            "kind": "leaf",
                            "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                            "operator": "equals",
                            "value": {"kind": "scalar", "value": "Lakers"},
                        },
                        "resultPredicate": {
                            "kind": "leaf",
                            "field": {
                                "targetObject": "",
                                "attribute": "average_minutes",
                                "location": "result",
                            },
                            "operator": "greater_than",
                            "value": {"kind": "scalar", "value": 30},
                        },
                    }
                },
            },
            "resolved_query": {
                "kind": "metric_query",
                "resolved": {
                    "rowPredicateResolved": {
                        "tag": "ResolvedRowPredicateLeafNode",
                        "contents": {"rowPredicateColumn": "team_name"},
                    },
                    "resultPredicateResolved": {
                        "tag": "ResolvedResultPredicateLeafNode",
                        "contents": {
                            "resultPredicateKey": "result_predicate_1",
                            "resultPredicateColumn": "minutes_played",
                        },
                    },
                },
            },
            "execution_plan": {
                "row_predicate": {
                    "kind": "leaf",
                    "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                    "operator": "equals",
                    "value": {"kind": "scalar", "value": "Lakers"},
                },
                "result_predicate": {
                    "kind": "leaf",
                    "field": {
                        "targetObject": "",
                        "attribute": "average_minutes",
                        "location": "result",
                    },
                    "operator": "greater_than",
                    "value": {"kind": "scalar", "value": 30},
                },
                "steps": [
                    {
                        "kind": "run_sql",
                        "sql": "SELECT *\nFROM ranked_entities\nWHERE result_predicate_1 > 30\nORDER BY metric_value DESC",
                        "analysis_spec": None,
                    }
                ],
            },
        }

        trace = build_predicate_trace(semantic_draft, planner_output)

        self.assertEqual(trace["draft_predicates"]["filters"][0]["field"], "team")
        self.assertEqual(trace["grounded_ir_predicates"]["rowPredicate"]["field"]["targetObject"], "Team")
        self.assertEqual(
            trace["resolved_predicates"]["resultPredicateResolved"]["contents"]["resultPredicateColumn"],
            "minutes_played",
        )
        self.assertEqual(trace["plan_predicates"]["result_predicate"]["operator"], "greater_than")
        self.assertEqual(
            trace["sql_predicates"],
            [{"step_index": 1, "kind": "run_sql", "clauses": ["WHERE result_predicate_1 > 30"]}],
        )

    def test_find_predicate_trace_uses_find_specific_fields(self) -> None:
        trace = build_predicate_trace(
            {"task": "find", "filters": [], "predicate": {"kind": "leaf", "field": "name", "op": "contains", "value": "Smith"}},
            {
                "query": {
                    "kind": "find_query",
                    "spec": {
                        "findPredicateTree": {
                            "kind": "leaf",
                            "field": {"targetObject": "Player", "attribute": "full_name", "location": "row"},
                            "operator": "contains",
                            "value": {"kind": "scalar", "value": "Smith"},
                        },
                        "findFilters": [],
                    },
                },
                "resolved_query": {
                    "kind": "find_query",
                    "resolved": {
                        "resolvedFindPredicateTree": {
                            "tag": "ResolvedFindPredicateLeafNode",
                            "contents": {"treePredicateColumn": "full_name"},
                        }
                    },
                },
                "execution_plan": {
                    "find_predicate_tree": {
                        "kind": "leaf",
                        "field": {"targetObject": "Player", "attribute": "full_name", "location": "row"},
                        "operator": "contains",
                        "value": {"kind": "scalar", "value": "Smith"},
                    },
                    "steps": [{"kind": "run_sql", "sql": "SELECT *\nWHERE f.full_name ILIKE '%Smith%'", "analysis_spec": None}],
                },
            },
        )

        self.assertEqual(trace["grounded_ir_predicates"]["findPredicateTree"]["operator"], "contains")
        self.assertEqual(
            trace["resolved_predicates"]["resolvedFindPredicateTree"]["contents"]["treePredicateColumn"],
            "full_name",
        )
        self.assertEqual(trace["sql_predicates"][0]["clauses"], ["WHERE f.full_name ILIKE '%Smith%'"])


if __name__ == "__main__":
    unittest.main()
