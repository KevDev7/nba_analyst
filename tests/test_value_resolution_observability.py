from __future__ import annotations

import unittest

from apps.assistant.value_resolution_observability import build_value_resolution_trace


class ValueResolutionObservabilityTests(unittest.TestCase):
    def test_combines_entity_and_predicate_value_resolutions(self) -> None:
        semantic_draft = {
            "value_resolution_trace": {
                "entity_resolutions": [
                    {
                        "raw_value": "Brunson",
                        "canonical_value": "Jalen Brunson",
                        "target_object": "Player",
                        "attribute": "full_name",
                        "entity_id": 1628973,
                        "source": "duckdb_entity_resolver",
                    }
                ]
            }
        }
        planner_output = {
            "query": {
                "kind": "metric_query",
                "spec": {
                    "sharedQuery": {
                        "rowPredicate": {
                            "kind": "leaf",
                            "field": {"targetObject": "Team", "attribute": "conference", "location": "row"},
                            "operator": "equals",
                            "value": {"kind": "scalar", "value": "Western"},
                        }
                    }
                },
            },
            "execution_plan": {
                "row_predicate": {
                    "kind": "leaf",
                    "field": {"targetObject": "Team", "attribute": "conference", "location": "row"},
                    "operator": "equals",
                    "value": {"kind": "scalar", "value": "west"},
                }
            },
        }

        trace = build_value_resolution_trace(semantic_draft, planner_output)

        self.assertEqual(trace["entity_resolutions"][0]["raw_value"], "Brunson")
        self.assertEqual(
            trace["predicate_value_resolutions"],
            [
                {
                    "raw_value": "Western",
                    "canonical_value": "west",
                    "target_object": "Team",
                    "attribute": "conference",
                    "source": "ontology_value_aliases",
                }
            ],
        )

    def test_traces_list_predicate_value_resolutions(self) -> None:
        trace = build_value_resolution_trace(
            {},
            {
                "query": {
                    "kind": "find_query",
                    "spec": {
                        "findPredicateTree": {
                            "kind": "leaf",
                            "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                            "operator": "in",
                            "value": {"kind": "list", "values": ["LA Lakers", "Salt Lake City Jazz"]},
                        }
                    },
                },
                "execution_plan": {
                    "find_predicate_tree": {
                        "kind": "leaf",
                        "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                        "operator": "in",
                        "value": {"kind": "list", "values": ["Lakers", "Jazz"]},
                    }
                },
            },
        )

        self.assertEqual(
            trace["predicate_value_resolutions"],
            [
                {
                    "raw_value": "LA Lakers",
                    "canonical_value": "Lakers",
                    "target_object": "Team",
                    "attribute": "team_name",
                    "source": "ontology_value_aliases",
                },
                {
                    "raw_value": "Salt Lake City Jazz",
                    "canonical_value": "Jazz",
                    "target_object": "Team",
                    "attribute": "team_name",
                    "source": "ontology_value_aliases",
                },
            ],
        )

    def test_omits_values_that_did_not_change(self) -> None:
        trace = build_value_resolution_trace(
            {},
            {
                "query": {
                    "kind": "metric_query",
                    "spec": {
                        "sharedQuery": {
                            "rowPredicate": {
                                "kind": "leaf",
                                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                                "operator": "equals",
                                "value": {"kind": "scalar", "value": "Lakers"},
                            }
                        }
                    },
                },
                "execution_plan": {
                    "row_predicate": {
                        "kind": "leaf",
                        "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                        "operator": "equals",
                        "value": {"kind": "scalar", "value": "Lakers"},
                    }
                },
            },
        )

        self.assertEqual(trace["predicate_value_resolutions"], [])


if __name__ == "__main__":
    unittest.main()
