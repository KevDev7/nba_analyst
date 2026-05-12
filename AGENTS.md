# NBA Analyst Agent Instructions

## Product Invariant

The ontology/schema contract is the primary grounding boundary for basketball answers.

## Do Not

- Do not bypass the ontology/Haskell planner for product data retrieval.
- Do not expose raw SQL to model-visible orchestration or public response payloads.
- Do not invent metrics, dimensions, filters, joins, entities, or data coverage.
- Do not claim lineup, on/off, play-by-play, shot-location, clutch, or possession-level support unless the ontology exposes it.
- Do not preserve restrictions above the schema contract unless they prevent a concrete correctness, security, or factuality failure.

## Safe Tool Order

1. Inspect catalog/coverage when capability is unclear.
2. Retrieve data through governed semantic query tooling.
3. Run Python analysis only over approved retrieved tables.
4. Generate artifacts from validated tables.
5. Compose answers from evidence and provenance.

## Slice 1 Boundary

The current Slice 1 architecture is intentionally behavior-preserving:

```text
pipeline.run_assistant
  -> orchestrator.run_assistant
  -> semantic_query.plan_execute
  -> existing semantic interpreter / Haskell planner / runtime / synthesis / artifacts
```

No SDK, model tool loop, sandboxed Python, Haskell changes, or new open-ended behavior belongs in Slice 1.

## Verification

Run focused checks after touching assistant orchestration:

```bash
python3 -m unittest \
  tests.test_cli_pipeline \
  tests.test_web_api \
  tests.test_deploy_runtime_path \
  tests.test_orchestrator_fast_path \
  tests.test_semantic_query_tool \
  tests.test_trace_schema \
  tests.test_chart_artifacts
```
