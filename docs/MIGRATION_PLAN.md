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

## Slice 4A: Tool Contract Stabilization

Status: implemented.

- Direct `semantic_draft` requests now default to raw and pass through deterministic preparation before Haskell planning.
- Internally generated drafts can be marked `prepared` to avoid double-normalizing explicit plan fields.
- Private execution-plan debug is gated by debug mode, trusted caller, and `NBA_ALLOW_PRIVATE_SQL_TRACE`.
- Semantic-query provenance records requested row limit and whether it is currently enforced.
- Python-analysis provenance records parent, derived-from, and output table ids.
- Brittle test helper ordering was fixed.

## Slice 4B: Generic Deterministic Multi-Call Plans

Status: implemented.

- Moved the hard-coded period-delta route out of `orchestrator.py`.
- Added `apps/assistant/routes/period_delta.py`.
- Added `PeriodDeltaPlan` and `PeriodSpec`.
- Generalized the deterministic route across supported subjects (`teams`, `players`), explicit seasons/season types, and configurable measures.
- Kept retrieval through `semantic_query.plan_execute`.
- Kept derived analysis through `python_analysis.run`.

## Slice 4C: Artifact, Catalog, And Governance Hardening

Status: implemented.

- `artifact_renderer.render` can now render derived `AnalysisTable` outputs.
- The period-delta route renders derived tables through `artifact_renderer.render`.
- `ontology_catalog.inspect` splits model-facing `subjects` from internal `fact_surfaces`.
- Semantic-query execution provenance now includes execution duration where available.
- Added `evals/orchestrator_question_bank.json` plus a trace-based test asserting expected tool sequence and forbidden raw paths.

## Slice 5A: Model-Orchestrator Dry Run

Status: implemented.

- Added `apps/assistant/model_orchestration/plans.py` for validated model-produced plans.
- Supported plan kinds start narrow: `simple_semantic_query`, `period_delta`, `artifact_request`, and `unsupported`.
- Model plans may name only governed tools: `ontology_catalog.inspect`, `semantic_query.plan_execute`, `python_analysis.run`, and `artifact_renderer.render`.
- Plans that reference raw SQL, arbitrary Python/code tools, or unsupported data surfaces are rejected unless represented as an `unsupported` refusal.
- Dry-run mode is gated by `NBA_ENABLE_MODEL_ORCHESTRATOR` plus `NBA_MODEL_ORCHESTRATOR_DRY_RUN`; it returns the validated plan and planned tool sequence without executing tools.

## Slice 5B: Gated Model Tool Execution

Status: implemented as a structured-plan executor.

- Model orchestration execution is disabled by default and requires `NBA_ENABLE_MODEL_ORCHESTRATOR`.
- Execution reuses existing governed tools rather than adding a raw SQL or arbitrary Python tool.
- Tool-call count is capped by the plan schema and executor.
- Planner failures or execution failures fall back to the deterministic orchestrator path.
- The deterministic fast path and deterministic `PeriodDeltaPlan` route remain available when model orchestration is disabled.

## Slice 5C: Grounded Answer Composer

Status: implemented behind a feature gate.

- Added a model-assisted answer composer that receives structured evidence tables, findings, and artifact summaries only.
- The composer does not receive raw SQL or database internals.
- Numeric/factual claims must include evidence references with `table_id`, `row_index`, and `columns`.
- Invalid or unsupported claims fall back to the deterministic table-first answer.
- The composer is disabled by default and requires `NBA_ENABLE_MODEL_ANSWER_COMPOSER`.

## Slice 5D: Model-Orchestration Evals

Status: implemented.

- Added `evals/model_orchestration_question_bank.json`.
- Added tests that assert expected model-plan tool sequences, forbidden raw paths, max tool-call count, and unsupported-surface refusals.
- Added tests proving model orchestration does not regress deterministic fallback behavior when the model planner fails.

## Slice 4: Governed Multi-Call Orchestrator

Status: stabilized deterministic route implemented.

Implemented first acceptance path:

```text
Which teams had the biggest increase in average points per game from the 2023-24 regular season to the 2024-25 regular season?
```

Current governed tool sequence:

```text
semantic_query.plan_execute  # prior season team average points
semantic_query.plan_execute  # current season team average points
python_analysis.run          # join_and_delta
artifact_renderer.render     # derived table artifacts
assistant response           # deterministic table-first summary
```

This route is intentionally additive:

- it does not replace the normal fast path;
- it does not use model tool-calling;
- it does not expose raw SQL;
- it does not let Python access DuckDB;
- it uses semantic drafts validated by Haskell for both retrievals.

Next improvements before model tool-calling:

- add more deterministic plan types only if they share the same structured-plan executor pattern;
- continue adding trace-based evals for each governed route;
- consider runtime-owned SQL execution metrics/caps before allowing any non-Haskell SQL author.

## Slice 6: Gated Arbitrary-Code Sandbox Prototype

Status: implemented as a gated prototype.

- Added `python_code` as a `python_analysis.run` operation kind, not a new raw Python tool.
- Gated code mode behind `NBA_ENABLE_PYTHON_CODE_SANDBOX`.
- Required `runtime="local_sandbox"` and declared input/output table schemas.
- Kept controlled operations available and preferred for common derived analyses.
- Added a subprocess runner using macOS `sandbox-exec` plus restricted builtins/imports.
- Sandbox input is serialized table data only; it receives no DuckDB connection, SQL, ontology internals, credentials, or arbitrary filesystem paths.
- Structured outputs are limited to tables, metrics, and findings.
- Output tables are validated against declared schemas and max row caps.
- Provenance records `code_hash`, parent table ids, output table ids, runtime id, timeout/execution metadata, stdout, and stderr.

Still out of scope:

- making arbitrary code the default analysis path;
- adding a separate model-visible raw Python tool;
- giving sandbox code database access;
- using sandbox output as final answer prose.

## Slice 7: Runtime SQL Governance V1

Status: implemented.

- Added a runtime `QueryExecutionResult` with SQL hash, execution duration, returned row count, requested row limit, enforced flag, and truncated flag.
- Added a defensive single-statement guard before DuckDB execution.
- Preserved read-only DuckDB execution and Haskell-only SQL authoring.
- Kept `run_sql(sql)` backward-compatible for direct tests/debug helpers while adding `run_sql_result(...)` for governed execution metadata.
- Threaded runtime-owned execution metadata into semantic-query trace/provenance without exposing raw SQL.

## Slice 8: Semantic Query Data Tables

Status: implemented.

- Split primary table projection into typed table data and UI artifact wrappers.
- `semantic_query.plan_execute` now builds `SemanticQueryTable` outputs from the typed `FinalAnswer` payload instead of scraping rendered artifacts.
- UI artifacts remain presentation outputs with the same public shape.
- Semantic-query table provenance now marks `source: "final_answer"` and carries execution-step provenance independently from artifacts.

## Slice 9: Haskell-Backed Ontology Catalog

Status: implemented.

- Added additive Haskell CLI mode `inspect-ontology-json --ontology <path>`.
- Haskell inspection emits subjects, fact surfaces, metrics, dimensions, filters, time grains, aliases, ranking polarity, and visibility from the validated ontology model.
- `ontology_catalog.inspect` now prefers Haskell inspection and keeps the Python/YAML catalog as a fallback.
- DuckDB coverage metadata remains Python-owned for now.

## Slice 10: Catalog/Snapshot Default Scope Provider

Status: implemented.

- Added a cached `DefaultScopeProvider` for season defaults.
- Current runtime defaults now come from DuckDB snapshot metadata when available.
- The existing `2025-26` / `regular_season` constants remain as fallbacks and compatibility exports.
- The current snapshot-derived defaults match previous product behavior, so user-facing assumption text is unchanged.
- Semantic-query trace/provenance records the default scope source and values.
