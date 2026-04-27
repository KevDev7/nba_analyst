# Test Map

The test suite is organized by behavior instead of historical slice number.

Some older behavior files still exercise the live CLI path without mocking the
LLM. Prefer focused deterministic modules for fast local regression checks, and
use live/snapshot suites deliberately when validating provider/data behavior.

## Core Entry And Contracts

- `test_cli_pipeline.py` covers the main terminal orchestration seam.
- `test_web_api.py` covers the localhost web/API adapter over the shared assistant boundary.
- `test_cli_semantic_draft_pipeline.py` covers semantic-draft-to-runtime end-to-end paths.
- `test_semantic_interpreter.py` covers prompt/schema parsing behavior.
- `test_entity_resolver.py` covers player/team entity resolution.
- `test_ontology_layer.py` covers ontology fixture validation.
- `test_question_bank.py` covers the question bank contract.

## Query Families

- `test_ranking_cli_variants.py` and `test_ranking_metric_queries.py` cover ranking/top-N behavior.
- `test_object_queries.py`, `test_object_query_limits.py`, and `test_object_query_metric_outputs.py` cover object-row behavior.
- `test_aggregate_queries.py` covers grouped aggregate behavior.
- `test_trend_cli_variants.py`, `test_trend_planning.py`, `test_trend_time_grain_contract.py`, and `test_trend_fact_surfaces.py` cover time-series behavior.
- `test_comparison_cli_variants.py`, `test_comparison_entity_aliases.py`, `test_comparison_planning.py`, and `test_comparison_generic_runtime.py` cover comparison behavior.
- `test_find_queries.py` covers filtering/find behavior.
- `test_season_queries.py` covers season-surface behavior across ranking/object outputs.

## Ontology-Grounded Boundaries

- `test_linked_filter_cli_queries.py`, `test_linked_filter_season_surfaces.py`, `test_linked_filter_object_queries.py`, `test_linked_filter_contract.py`, `test_linked_filter_generic_grounding.py`, and `test_linked_filter_reachable_attributes.py` cover linked-filter grounding.
- `test_query_shape_validation.py`, `test_metric_contract_validation.py`, `test_dimension_contract_validation.py`, and `test_filter_contract_validation.py` cover schema/ontology boundary failures.
- `test_semantic_draft_module.py` and `test_semantic_draft_grounding.py` cover Haskell grounding from semantic drafts.

## Slower Truth Evaluation

- `test_truth_eval_snapshot.py` is snapshot/truth-eval style coverage. It may depend on live LLM behavior or current data snapshot assumptions, so treat it differently from the fast deterministic regression suite.
