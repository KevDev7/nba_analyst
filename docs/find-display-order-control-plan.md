# Find Display / Order Control Plan

## Goal

Let Find queries return the columns and ordering the user asked for, grounded
through the ontology rather than through phrase-specific corridors.

Example target:

```text
Find Lakers games over 120 points and show date, opponent, score, and margin,
sorted newest first.
```

This should produce matching game rows where:

- requested display columns lead the table
- predicate-context columns can still appear when useful
- explicit sort intent controls SQL ordering
- failures happen only when the ontology/data snapshot cannot support the
  requested field, path, predicate, or order

## Current State

Find already has a dedicated `FindQuery` shape and strong predicate support.
Slice 1 added requested display projection. Slice 2 added role-aware linked
display for fields such as `opponent`. Slice 3 added ontology-grounded Find
order intent. The remaining limitation is mainly presentation/docs hardening:

- `dimensions` from the semantic draft are now used as requested Find display
  columns when they resolve to public ontology attributes.
- `FindQuery` still keeps planner-selected defaults when no display fields are
  requested.
- Role-specific displays like `opponent` now resolve through ontology link
  roles, such as `team_game_opponent_team`.
- SQL now orders Find rows by user-requested grounded order fields when the
  draft provides them.
- If no order is requested, SQL keeps the planner default of ordering by the
  first display column descending.
- For `last_n_games`, SQL still selects the latest N games first, then applies
  the requested final display order to those selected rows.

## Design Principles

- The ontology/schema contract is the safety boundary.
- Requested display fields should be allowed when they resolve to public
  ontology attributes through a valid path.
- Requested ordering should be allowed when it resolves to a public ontology
  attribute already reachable from the Find fact surface.
- If a requested display/order field cannot be grounded, fail clearly instead
  of silently dropping it.
- If the user does not request display fields, keep planner-selected defaults.
- If the user does not request ordering, keep a sensible planner default.

## Slice 1: Find Display Projection

Use user-requested `dimensions` as Find display intent.

Status: implemented.

Implementation shape:

- Preserve `dimensions` from the semantic draft for Find grounding.
- Resolve requested display phrases against public ontology attributes.
- Allow display attributes on the fact object and reachable linked objects, not
  only the target object.
- Keep default Find display columns when no display intent is provided.
- Keep predicate-context columns available when useful.

Example unlocked:

```text
Find Lakers games over 120 points and show date, score, point differential.
```

Likely files:

- `services/ontology-hs/src/QueryModel/SemanticDraft/Find.hs`
- `services/ontology-hs/src/QueryModel/SemanticDraft/Types.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile/Sql/Find.hs`
- `tests/test_find_queries.py`
- `tests/test_semantic_draft_grounding.py`

## Slice 2: Role-Aware Linked Display

Support display fields that imply a specific relationship role, especially
`opponent`.

Status: implemented.

Implementation shape:

- Resolve display fields through ontology paths with link role awareness.
- Prefer explicit role/path matches when the user asks for role-bearing fields
  such as `opponent`.
- Avoid relying on whichever same-object path `findPath` returns first when
  multiple links point to the same object.
- Ground `opponent` for TeamGame through the `team_game_opponent_team` link.

Example unlocked:

```text
Find Lakers games over 120 points and show date, opponent, score.
```

Likely files:

- `services/ontology-hs/src/OntologyLayer/Graph.hs`
- `services/ontology-hs/src/QueryModel/SemanticDraft/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile/Sql/Find.hs`
- `tests/test_find_queries.py`

## Slice 3: Find Order Control

Make Find ordering explicit and grounded.

Status: implemented.

Implementation shape:

- Parse draft `order` entries into real Haskell values instead of throwaway
  freeform objects.
- Add Find-specific order intent to Query IR and resolved Find queries.
- Resolve order fields through the same ontology-grounded display/order
  mechanism.
- Compile `ORDER BY` using the requested field and direction.
- Support natural directions such as newest/oldest through the LLM draft as
  ordinary `asc` / `desc` order intent.
- Keep planner default order only when the user does not request one.

Example unlocked:

```text
Find Lakers games over 120 points and show date, opponent, score, sorted newest first.
```

Likely files:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft/Types.hs`
- `services/ontology-hs/src/QueryModel/IR.hs`
- `services/ontology-hs/src/QueryModel/SemanticDraft/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile/Sql/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Plan.hs`
- `services/runtime-py/runtime/AnalysisRuntime/models.py`
- `tests/test_find_queries.py`
- `tests/test_semantic_interpreter.py`

## Slice 4: Prompt, Presentation, Docs, Hardening

Tie the feature into the user-facing path and remove stale wording.

Status: implemented.

Implementation shape:

- Carry grounded Find order metadata through the execution plan and Python
  runtime result payload.
- Use grounded Find order metadata in `Interpreted as:`.
- Keep debug/observability showing draft order, grounded order, and SQL order.
- Ensure answer formatting keeps requested column order.
- Update contracts and docs so Find display/order is no longer described as
  limited.
- Add end-to-end mocked CLI tests for display projection and ordering.

Example final check:

```text
python3 apps/cli/main.py "Find Lakers games over 120 points and show date, opponent, score, and margin, sorted newest first" --debug
```

Likely files:

- `apps/cli/semantic_interpreter.py`
- `services/runtime-py/runtime/AnswerSynthesis/format_response.py`
- `services/runtime-py/runtime/AnswerSynthesis/interpretation_summary.py`
- `contracts/query_ir.md`
- `contracts/execution_plan.md`
- `contracts/final_answer.md`
- `docs/query-model.md`
- `docs/grounded-planning.md`
- `tests/test_find_queries.py`
- `tests/test_interpretation_summary.py`

## Verification

Run focused checks after each slice:

```bash
cabal build -v0
python3 -m pytest tests/test_find_queries.py tests/test_semantic_draft_grounding.py -q
```

Run broader maintained app checks after final hardening:

```bash
python3 -m pytest tests -q
```

Known caveat: full repo pytest may require optional pipeline dependencies such
as `pbpstats` and `nba_api`.
