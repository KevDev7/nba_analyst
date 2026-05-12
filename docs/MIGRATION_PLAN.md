# Migration Plan

The long-term target is a bounded orchestrator with governed tools:

```text
model judgment above the boundary
ontology/Haskell/runtime governance below the boundary
```

## Slice 1: Deterministic Orchestrator Seam

Status: implemented.

Goal: express the current pipeline as one governed tool call with trace/provenance, without changing product behavior.

Flow:

```text
apps.assistant.pipeline.run_assistant
  -> apps.assistant.orchestrator.run_assistant
  -> apps.assistant.tools.semantic_query.plan_execute
  -> existing semantic interpreter / Haskell planner / runtime / synthesis / artifacts
```

Out of scope:

- LLM tool-calling loop.
- OpenAI Agents SDK.
- Python sandbox.
- Haskell planner changes.
- new open-ended analysis behavior.
- SQL parser/validator.

## Slice 2: Catalog And Artifact Tools

Status: implemented.

- Added `ontology_catalog.inspect` as a read-only Python catalog backed by `semantic-gold.yaml` and DuckDB coverage metadata.
- Moved artifact generation behind `artifact_renderer.render`.
- Kept UI artifact JSON unchanged.
- Left hard-coded default season behavior unchanged; catalog-derived defaults are now visible for a later behavior-changing slice.

## Slice 3: Controlled Derived Analysis

Status: implemented.

- Extended `services/runtime-py/runtime/AnalysisTools` with controlled derived-table outputs.
- Added `join_and_delta` for period/table deltas.
- Added `rank_extremes` for deterministic sorted derived tables.
- Added assistant wrapper `apps/assistant/tools/python_analysis.py`.
- Added a first acceptance-style test for season-over-season team average points increases.

Candidate acceptance question:

```text
Which teams had the biggest increase in average points per game from the 2023-24 regular season to the 2024-25 regular season?
```

Longer-term tool sequence for richer presentation:

```text
semantic_query.plan_execute
semantic_query.plan_execute
python_analysis.run
artifact_renderer.render
answer_composer.compose
```

## Slice 4: Governed Multi-Call Orchestrator

Status: initial route implemented.

Implemented first acceptance path:

```text
Which teams had the biggest increase in average points per game from the 2023-24 regular season to the 2024-25 regular season?
```

Current governed tool sequence:

```text
semantic_query.plan_execute  # prior season team average points
semantic_query.plan_execute  # current season team average points
python_analysis.run          # join_and_delta
assistant response           # deterministic table-first summary
```

This route is intentionally additive:

- it does not replace the normal fast path;
- it does not use model tool-calling;
- it does not expose raw SQL;
- it does not let Python access DuckDB;
- it uses semantic drafts validated by Haskell for both retrievals.

Next improvements:

- route more period-over-period metric deltas through the same tool pattern;
- render derived-analysis tables/charts through the artifact renderer;
- promote the multi-call trace into the normal debug schema for CLI/web display.

## Later: Model Tool Loop And Sandbox

Only after tool contracts, trace records, and evals are stable:

- Add LLM orchestrator tool calls.
- Avoid double LLM calls by allowing orchestrator-emitted semantic drafts.
- Add sandboxed Python over approved retrieved tables.
- Keep sandboxed Python away from raw DuckDB access.
