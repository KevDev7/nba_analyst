# NBA Analyst Agent Instructions

## Product Invariant

The ontology/schema contract is the primary grounding boundary for basketball answers.
Haskell is the only SQL author for product data retrieval. Runtime SQL governance
exists to safely execute Haskell-generated SQL; it is not a future opening for
model-authored, user-authored, Python-authored, or sandbox-authored SQL.

## Do Not

- Do not bypass the ontology/Haskell planner for product data retrieval.
- Do not add model-authored, user-authored, Python-authored, or sandbox-authored SQL paths.
- Do not add SQL repair, SQL transformation, SQL snippets, or DuckDB/warehouse inspection to model-visible orchestration.
- Do not expose raw SQL to model-visible orchestration or public response payloads.
- Do not add a raw Python/code execution tool; sandboxed code, when enabled, must stay inside `python_analysis.run`.
- Do not invent metrics, dimensions, filters, joins, entities, or data coverage.
- Do not claim lineup, on/off, play-by-play, shot-location, clutch, or possession-level support unless the ontology exposes it.
- Do not preserve restrictions above the schema contract unless they prevent a concrete correctness, security, or factuality failure.

## Safe Tool Order

1. Inspect catalog/coverage when capability is unclear.
2. Retrieve data through governed semantic query tooling.
3. Run Python analysis only over approved retrieved tables.
4. Generate artifacts from validated tables.
5. Compose answers from evidence and provenance.

## Python Code Sandbox

Arbitrary code analysis is disabled by default and must remain gated by `NBA_ENABLE_PYTHON_CODE_SANDBOX`.

Code mode may analyze only approved input tables. It must not receive raw SQL, DuckDB/database handles, credentials, environment variables, network access, or arbitrary filesystem access.
It must not import or use database clients, author SQL strings, or inspect warehouse/schema internals.

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
