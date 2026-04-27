# Scope 1 Implementation Plan

This plan explains how to finish the Scope 1 PRD.

The PRD defines what "done" means. This file defines the implementation path.

## Target

Scope 1 is complete when the terminal can answer one-step questions across all five families:

```text
rank
trend
aggregate
find
compare
```

Each family must work through:

```text
natural-language question
-> semantic draft
-> typed Query IR
-> ontology-grounded validation/resolution
-> execution plan
-> Python runtime result
-> final terminal answer
```

## Horizontal Work Areas

These are the main layers that will be touched.

### 1. Semantic Draft / Query Model

Files:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft.hs`
- `services/ontology-hs/src/QueryModel/IR.hs`

Work:

- Keep the LLM output in user-facing semantic terms.
- Normalize all five draft families into typed Query IR.
- Avoid hardcoded phrase/path restrictions above the ontology layer.
- Extend IR only when a family cannot be represented cleanly by the current model.

### 2. Grounded Planning

Files:

- `services/ontology-hs/src/GroundedPlanning/Validation.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/*`
- `services/ontology-hs/src/GroundedPlanning/Resolve.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/*`

Work:

- Validate each family against ontology capability.
- Resolve concrete objects, metrics, dimensions, paths, filters, and formulas.
- Move shared behavior into `Common.hs` only when it is truly shared.
- Remove or justify hardcoded restrictions above the ontology layer.

### 3. Plan Compilation

Files:

- `services/ontology-hs/src/GroundedPlanning/Compile.hs`
- `services/ontology-hs/src/GroundedPlanning/Plan.hs`

Work:

- Compile each resolved family into an execution plan.
- Add result shapes only when needed.
- Keep SQL generation grounded in resolved ontology paths and fields.

### 4. Python Runtime

Files:

- `services/runtime-py/runtime/AnalysisRuntime/models.py`
- `services/runtime-py/runtime/AnalysisRuntime/runner.py`
- `services/runtime-py/runtime/AnalysisRuntime/query_engine.py`
- `services/runtime-py/runtime/AnalysisRuntime/state.py`
- `services/runtime-py/runtime/AnalysisRuntime/analysis.py`

Work:

- Execute each plan shape.
- Add runtime result models for new result shapes when needed.
- Support SQL-only plans and SQL-plus-Python plans.
- Keep intermediate state available for multi-step execution.

### 5. Answer Synthesis

Files:

- `services/runtime-py/runtime/AnswerSynthesis/package_results.py`
- `services/runtime-py/runtime/AnswerSynthesis/synthesize.py`
- `services/runtime-py/runtime/AnswerSynthesis/format_response.py`
- `services/runtime-py/runtime/AnswerSynthesis/response_models.py`

Work:

- Package runtime results into grounded synthesis payloads.
- Generate summaries for each result shape.
- Format terminal-readable tables and comparison sections.
- Avoid inventing analysis not present in runtime results.

### 6. Tests

Files:

- `tests/test_semantic_interpreter.py`
- new or existing `tests/test_slice_*.py`
- shared helpers in `tests/planner_helpers.py`

Work:

- Add one end-to-end terminal-style acceptance test per family.
- Add negative tests for ontology/data-driven failures.
- Add regression tests for removed hardcoded restrictions.

## Vertical Slices

Implementation should proceed by vertical slices rather than by horizontal layer.

Each slice should go from user question to final terminal answer before the next family is started.

## Slice 1: Rank Hardening

Goal:

Make the existing rank family satisfy the Scope 1 failure contract.

Acceptance question:

```text
Show me the top 10 players by points over the last 10 games
```

Primary files:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Rank.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Rank.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile.hs`
- `services/runtime-py/runtime/AnalysisRuntime/*`
- `services/runtime-py/runtime/AnswerSynthesis/*`

Work:

- Verify rank works from natural language through terminal answer.
- Confirm limits are not restricted to only a few values.
- Confirm alternate phrasing like "top NBA players by points these last ten games" still grounds.
- Audit remaining rank restrictions and justify or remove them.

Done when:

- rank acceptance test passes end to end
- at least one wording-variation test passes
- rank failures are ontology/data/ambiguity failures, not hardcoded phrase failures

## Slice 2: Trend End To End

Goal:

Make trend questions work from natural language through terminal answer.

Acceptance question:

```text
Show me monthly points by team over the past year
```

Primary files:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft.hs`
- `services/ontology-hs/src/QueryModel/IR.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Trend.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Trend.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile.hs`
- `services/runtime-py/runtime/AnalysisRuntime/models.py`
- `services/runtime-py/runtime/AnalysisRuntime/runner.py`
- `services/runtime-py/runtime/AnswerSynthesis/synthesize.py`
- `services/runtime-py/runtime/AnswerSynthesis/format_response.py`

Work:

- Normalize trend semantic drafts into typed IR.
- Ground metric, time window, time grain, and optional grouping through ontology.
- Compile trend SQL from resolved ontology surfaces.
- Return time-series rows and terminal table.

Done when:

- trend acceptance test passes end to end
- unsupported trend failures point to missing ontology/data surfaces

## Slice 3: Compare End To End

Goal:

Make comparison questions work from natural language through terminal answer.

Acceptance question:

```text
Compare Brunson and Haliburton scoring over the last 10 games
```

Primary files:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft.hs`
- `services/ontology-hs/src/QueryModel/IR.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Compare.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Compare.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile.hs`
- `services/runtime-py/runtime/AnalysisRuntime/analysis.py`
- `services/runtime-py/runtime/AnswerSynthesis/synthesize.py`
- `services/runtime-py/runtime/AnswerSynthesis/format_response.py`

Work:

- Normalize compare semantic drafts into typed IR.
- Resolve named entities through ontology/data support rather than trusting the LLM to invent IDs.
- Compile SQL plus Python analysis plan when needed.
- Return comparison result and terminal comparison section.

Done when:

- compare acceptance test passes end to end
- entity resolution failures are explicit and grounded
- comparison restrictions are justified or removed

## Slice 4: Aggregate End To End

Goal:

Make aggregate questions work from natural language through terminal answer.

Acceptance question:

```text
Calculate average points by team over the last 10 games
```

Primary files:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft.hs`
- `services/ontology-hs/src/QueryModel/IR.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Aggregate.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Aggregate.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile.hs`
- `services/ontology-hs/src/GroundedPlanning/Plan.hs`
- `services/runtime-py/runtime/AnalysisRuntime/models.py`
- `services/runtime-py/runtime/AnalysisRuntime/runner.py`
- `services/runtime-py/runtime/AnswerSynthesis/*`

Work:

- Decide whether aggregate can reuse metric-query IR or needs a clearer aggregate shape.
- Validate grouping dimensions and metric aggregation through ontology.
- Resolve grouping paths and metric formula.
- Compile grouped aggregate SQL.
- Return grouped summary rows.

Done when:

- aggregate acceptance test passes end to end
- aggregate is not treated as a disguised rank unless the output shape truly matches

## Slice 5: Find End To End

Goal:

Make find/filter+join questions work from natural language through terminal answer.

Acceptance question:

```text
Find games where the Lakers scored over 120 points
```

Primary files:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft.hs`
- `services/ontology-hs/src/QueryModel/IR.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile.hs`
- `services/ontology-hs/src/GroundedPlanning/Plan.hs`
- `services/runtime-py/runtime/AnalysisRuntime/models.py`
- `services/runtime-py/runtime/AnalysisRuntime/runner.py`
- `services/runtime-py/runtime/AnswerSynthesis/*`

Work:

- Add or reuse IR for row/object retrieval with filters.
- Validate target object and filters through ontology.
- Resolve linked filters and required output fields.
- Compile SQL that returns matching rows/entities.
- Format a terminal table.

Done when:

- find acceptance test passes end to end
- unsupported find questions fail because the ontology/data cannot ground them

## Slice 6: Restriction Audit And Scope 1 Closure

Goal:

Make sure the system fails for the right reasons.

Primary files:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/*`
- `services/ontology-hs/src/GroundedPlanning/Resolve/*`
- `services/ontology-hs/src/GroundedPlanning/Compile.hs`
- `tests/*`

Work:

- Search for "currently", "only", "unsupported", and hardcoded family restrictions.
- For each restriction, either remove it or document why it is required.
- Add negative tests for missing ontology/data paths.
- Add wording-variation tests for the five families.

Done when:

- all five acceptance tests pass
- failures align with the PRD failure contract
- remaining restrictions have clear correctness or safety justification

## Current Recommended Order

1. Rank hardening
2. Trend end to end
3. Compare end to end
4. Aggregate end to end
5. Find end to end
6. Restriction audit and Scope 1 closure

Trend and compare come before aggregate/find because more lower-level planner/runtime support already exists for them.

