# Semantic Construction Refactor Plan

## Goal

Introduce a clearer boundary between the LLM draft contract and the ontology-backed construction logic that builds typed Query IR.

This is primarily a behavior-preserving architecture refactor. The expected output should remain the same:

```text
SemanticDraft JSON
-> semanticDraftToQuery
-> QueryModel.IR.Query
-> GroundedPlanning
-> ExecutionPlan
```

The refactor should make the codebase easier to extend later with richer semantic construction:

```text
scan user-facing concepts
-> match against ontology candidates
-> classify/build family intent
-> build typed IR
```

## Non-Goals

- Do not change generated SQL behavior intentionally.
- Do not add new ontology restrictions above the schema contract.
- Do not replace the LLM with deterministic parsing.
- Do not split `QueryModel.IR` in this project unless a later pass proves the contract itself is becoming hard to use.
- Do not add phrase-specific corridors while moving code.

## Starting Shape

```text
services/ontology-hs/src/QueryModel/
  IR.hs
  SemanticDraft.hs
  SemanticDraft/
    Aggregate.hs
    CandidateSelection.hs
    Compare.hs
    FilterGrounding.hs
    Filters.hs
    Find.hs
    Find/
      Display.hs
      Predicate.hs
    Grouping.hs
    Match.hs
    MatchAccessors.hs
    MeasureMatch.hs
    Normalize.hs
    Object.hs
    PredicateGrounding.hs
    Rank.hs
    ResultFilterGrounding.hs
    Trend.hs
    Types.hs
```

At the start of this refactor, the `SemanticDraft` namespace owned both:

- draft JSON decoding and normalization
- ontology-backed matching, grounding, and IR construction

That worked, but it blurred the mental model.

## Target Shape

Target final shape:

```text
services/ontology-hs/src/QueryModel/
  IR.hs
  SemanticDraft.hs

  SemanticDraft/
    Types.hs
    Normalize.hs
    Filters.hs

  SemanticConstruction/
    Types.hs
    CandidateSelection.hs
    Grouping.hs
    Match.hs
    MatchAccessors.hs
    MeasureMatch.hs
    PredicateGrounding.hs
    FilterGrounding.hs
    ResultFilterGrounding.hs

    Find/
      Display.hs
      Predicate.hs

    Build/
      Rank.hs
      Aggregate.hs
      Trend.hs
      Find.hs
      Compare.hs
      Object.hs
```

Plain English:

```text
SemanticDraft/
  What did the LLM send us?

SemanticConstruction/
  What does that draft mean against our ontology?

IR.hs
  What typed query are we handing to grounded planning?
```

## Slice 1: Construction Core Namespace

Move shared ontology matching and candidate-selection helpers into `QueryModel.SemanticConstruction`.

Implemented moves:

```text
QueryModel.SemanticDraft.Match
-> QueryModel.SemanticConstruction.Match

QueryModel.SemanticDraft.MeasureMatch
-> QueryModel.SemanticConstruction.MeasureMatch

QueryModel.SemanticDraft.MatchAccessors
-> QueryModel.SemanticConstruction.MatchAccessors

QueryModel.SemanticDraft.CandidateSelection
-> QueryModel.SemanticConstruction.CandidateSelection

QueryModel.SemanticDraft.Grouping
-> QueryModel.SemanticConstruction.Grouping
```

Expected behavior:

- Same semantic draft inputs produce the same query IR.
- Same planner output and SQL.

Verification:

```bash
cabal v2-build -v0 ontology-hs
python3 -m unittest tests.test_semantic_draft_grounding tests.test_multi_dimensional_grouping
```

## Slice 2: Construction Types Boundary

Split draft input types from grounded construction types.

Keep draft JSON/input types in:

```text
QueryModel.SemanticDraft.Types
```

Move grounded/intermediate construction types into:

```text
QueryModel.SemanticConstruction.Types
```

Implemented moved types:

```text
GroundedRanking
GroundedTrend
GroundedComparison
GroundedAggregate
GroundedFind
SemanticGroupingDimension
TimeScope
```

Expected behavior:

- No behavior change.
- The draft namespace becomes more clearly about the LLM contract.

Verification:

```bash
cabal v2-build -v0 ontology-hs --ghc-options=-Wall
python3 -m unittest tests.test_semantic_draft_module tests.test_semantic_draft_grounding
```

## Slice 3: Predicate And Filter Grounding Boundary

Move predicate/filter grounding logic into construction.

Implemented moves:

```text
QueryModel.SemanticDraft.PredicateGrounding
-> QueryModel.SemanticConstruction.PredicateGrounding

QueryModel.SemanticDraft.FilterGrounding
-> QueryModel.SemanticConstruction.FilterGrounding

QueryModel.SemanticDraft.ResultFilterGrounding
-> QueryModel.SemanticConstruction.ResultFilterGrounding

QueryModel.SemanticDraft.Find.Predicate
-> QueryModel.SemanticConstruction.Find.Predicate
```

Expected behavior:

- Same row predicates.
- Same result predicates.
- Same find predicate trees.
- Same value canonicalization behavior downstream.

Verification:

```bash
python3 -m unittest \
  tests.test_semantic_draft_grounding \
  tests.test_row_predicate_migration \
  tests.test_find_queries
```

## Slice 4: Family Builders Boundary

Move family-specific draft-to-IR builders into construction.

Implemented moves:

```text
QueryModel.SemanticDraft.Rank
-> QueryModel.SemanticConstruction.Build.Rank

QueryModel.SemanticDraft.Aggregate
-> QueryModel.SemanticConstruction.Build.Aggregate

QueryModel.SemanticDraft.Trend
-> QueryModel.SemanticConstruction.Build.Trend

QueryModel.SemanticDraft.Find
-> QueryModel.SemanticConstruction.Build.Find

QueryModel.SemanticDraft.Compare
-> QueryModel.SemanticConstruction.Build.Compare

QueryModel.SemanticDraft.Object
-> QueryModel.SemanticConstruction.Build.Object

QueryModel.SemanticDraft.Find.Display
-> QueryModel.SemanticConstruction.Find.Display
```

`QueryModel.SemanticDraft` should remain the public doorway:

```haskell
semanticDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
```

Expected behavior:

- Public API stays the same.
- Callers still import `QueryModel.SemanticDraft`.
- Builders now live in the namespace that describes what they actually do.

Verification:

```bash
python3 -m unittest \
  tests.test_ranking_metric_queries \
  tests.test_aggregate_queries \
  tests.test_trend_cli_variants \
  tests.test_find_queries \
  tests.test_comparison_planning \
  tests.test_object_query_metric_outputs
```

## Slice 5: Cleanup And Hardening

Remove stale modules/imports, update cabal, update docs/comments, and run broad regression coverage.

Checklist:

- Remove old `QueryModel.SemanticDraft.*` implementation modules that were moved.
- Ensure `ontology-hs.cabal` only lists current modules.
- Keep `QueryModel.SemanticDraft` as the stable public facade.
- Update docs that describe the draft-to-IR path.
- Confirm no behavior drift in representative CLI and planner tests.

Verification:

```bash
cabal v2-build -v0 ontology-hs --ghc-options=-Wall
python3 -m unittest discover tests
```

Latest verification:

```bash
cabal v2-build -v0 ontology-hs --ghc-options=-Wall
python3 -m unittest discover tests
```

Result:

```text
346 tests OK
```

## Completion Criteria

This refactor is complete when:

- `SemanticDraft/` mostly contains draft JSON types, normalization, and input-shape helpers.
- `SemanticConstruction/` owns ontology-backed matching, grounding, candidate selection, and family builders.
- `QueryModel.IR` remains unchanged unless separately justified.
- Existing semantic draft, planner, runtime, and CLI tests pass.
- No new product restriction is introduced above the ontology/schema contract.
