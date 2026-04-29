# Predicate Model Plan

This plan describes the long-term path for replacing the current flat filter
lanes with a shared ontology-grounded predicate model.

The goal is to support more natural filter language without adding
phrase-specific corridors above the ontology layer.

Examples this should eventually unlock:

- `players on the Lakers or Warriors`
- `games between Jan 1 and Feb 1`
- `teams not in the West`
- `players whose name contains Smith`
- `players with minutes between 20 and 30`
- `teams with average points between 110 and 120`

## Why This Exists

Before this plan, the codebase had several separate predicate-like concepts:

- `LinkedFilter`
- `ResultFilter`
- `FindPredicate`
- time/window `Filter`

Those were useful stepping stones, but they were not one shared predicate
language. The codebase now uses the shared predicate tree as the internal
contract for row, result, and find predicates.

Today the system mostly represents filters as:

```text
filter A AND filter B AND filter C
```

with scalar operators:

```text
=
>
>=
<
<=
```

That is enough for simple questions such as:

```text
players with minutes over 30
teams with win percentage above .600
games where Lakers scored over 120 points
```

It is not enough for richer filter language:

```text
team is Lakers or Warriors
team is not in the West
name contains Smith
points between 20 and 30
```

Those require a predicate tree, not only a flat list.

## Product Principle

The schema contract remains the safety boundary.

The system should fail only when:

- the ontology cannot ground the requested object, metric, dimension, attribute,
  or link
- the local data snapshot cannot support the requested field or path
- the question is outside the supported assistant families
- the requested predicate shape cannot be compiled safely yet

The system should not fail because:

- a family has a hand-written filter corridor
- a filter phrase was not in a hardcoded list
- only equality filters were wired for a family that could safely support more
- the same predicate capability exists in one family but not another

## Conceptual Model

The long-term shape should separate time scope from generic predicates.

```text
TimeScope = when are we looking?
Predicate = which rows or results are allowed through?
```

Time scope should stay separate because scopes such as `last_n_games` may
require windowing/ranking logic, not just a normal SQL `WHERE` condition.

Generic predicates should become a tree:

```text
Predicate
-> leaf predicate
-> AND predicate
-> OR predicate
-> NOT predicate
```

Plain English:

```text
Leaf predicate = one condition
AND predicate = all child conditions must be true
OR predicate = at least one child condition must be true
NOT predicate = invert one condition
```

Possible Haskell-style shape:

```haskell
data Predicate
  = PredicateLeaf PredicateField PredicateOperator PredicateValue
  | PredicateAnd [Predicate]
  | PredicateOr [Predicate]
  | PredicateNot Predicate
```

The predicate field should be grounded against ontology truth:

```text
target object
attribute
source column
attribute kind
relationship path
row/result location
```

The predicate operator should eventually support:

```text
equals
not equals
greater than
greater than or equal
less than
less than or equal
in
not in
between
contains
```

The predicate value should support:

```text
text
integer
decimal
date
boolean
list
range
```

## Important Boundary

Row predicates and result predicates should use the same conceptual predicate
tree, but they should not be validated in the exact same location.

Row predicates apply before grouping:

```text
WHERE player_game.minutes_played > 30
```

Result predicates apply after grouping:

```text
HAVING AVG(player_game.minutes_played) > 30
```

So the shared model should support both, but validation must know whether a
predicate is row-level or result-level.

## Current Files To Touch Over Time

Semantic draft:

- `apps/cli/semantic_interpreter.py`
- `services/ontology-hs/src/QueryModel/SemanticDraft/Types.hs`
- `services/ontology-hs/src/QueryModel/SemanticDraft/FilterGrounding.hs`
- `services/ontology-hs/src/QueryModel/SemanticDraft/ResultFilterGrounding.hs`
- `services/ontology-hs/src/QueryModel/SemanticDraft/Find.hs`

Query model:

- `services/ontology-hs/src/QueryModel/IR.hs`

Grounded planning:

- `services/ontology-hs/src/GroundedPlanning/Validation/Common/RowPredicates.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Common/ResultPredicates.hs`
- `services/ontology-hs/src/GroundedPlanning/Validation/Find.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Common/RowPredicates.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Common/ResultPredicates.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Find.hs`

SQL compilation:

- `services/ontology-hs/src/GroundedPlanning/Compile/Sql/Common.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile/Sql/Find.hs`
- family SQL compilers under `services/ontology-hs/src/GroundedPlanning/Compile/Sql/`

Runtime and synthesis:

- `services/runtime-py/runtime/AnalysisRuntime/models.py`
- `services/runtime-py/runtime/AnswerSynthesis/response_models.py`
- `services/runtime-py/runtime/AnswerSynthesis/interpretation_summary.py`

## Slice 1: Predicate Contract

Status: complete.

Purpose:

Introduce the shared predicate contract without changing product behavior.

Work:

- Add shared predicate types.
- Add typed predicate values for scalar, list, and range values.
- Add predicate operators for the long-term language.
- Add JSON parsing/encoding tests.
- Keep existing behavior working while introducing the shared predicate tree.

Done when:

- The codebase has a typed predicate tree available.
- Existing tests still pass.
- No user-facing behavior changes yet.

## Slice 2: Find Predicate Migration

Status: complete.

Purpose:

Move `find` queries onto the shared predicate tree first.

Why first:

Find queries are naturally row-retrieval questions, so they are the cleanest
place to prove the predicate model.

Work:

- Let find drafts carry or lower into predicate trees.
- Ground predicate leaves against ontology attributes and paths.
- Support `AND`, `OR`, and `NOT` for find predicates.
- Support `equals`, `not equals`, `in`, `not in`, `between`, and `contains`
  where type-safe.
- Compile find predicate trees into SQL with correct parentheses.
- Preserve predicate-tree fields in find result columns when they add useful
  row context and do not duplicate existing display columns.
- Carry grounded find predicate-tree metadata through runtime and answer
  synthesis.
- Preserve existing simple find behavior.

Done when:

- Find can answer row-filter questions with richer predicate language.
- Predicate failures are ontology/type/compile failures, not phrase corridors.
- `Interpreted as:` can describe find predicate trees without flattening `OR`
  and `NOT` into misleading `AND` wording.

Example acceptance questions:

- `Find players whose name contains Smith`
- `Find Lakers or Warriors games in the 2025-26 regular season`
- `Find games where team score is between 110 and 120`
- `Find teams not in the West`

## Slice 3: Row Predicate Migration

Status: complete.

Purpose:

Move non-find row-level filters onto the shared predicate model.

Affected families:

- rank
- object
- aggregate
- trend
- compare

Work:

- Move row-filter behavior into row predicate trees.
- Keep row predicates separate from result predicates.
- Reuse ontology path resolution for predicate leaves.
- Support richer operators for public dimensions and public measures where
  safe.
- Reuse value canonicalization for scalar, list, and range values.
- Carry row-predicate metadata through runtime and answer synthesis so
  `Interpreted as:` can describe `OR`, `NOT`, `IN`, `BETWEEN`, and `CONTAINS`
  truthfully.

Done when:

- The non-find families can share the same row predicate model.
- Existing equality and numeric predicate behavior still works.
- `OR`, `NOT`, `IN`, `BETWEEN`, and `CONTAINS` are available where the ontology
  and type rules allow them.

Example acceptance questions:

- `Rank players by points for the Lakers or Warriors`
- `Show teams not in the West with their wins`
- `Average points by team where conference is East or West`
- `Compare Brunson and Tatum where minutes are over 25`

## Slice 4: Result Predicate Migration

Status: complete.

Purpose:

Move aggregate/result filters onto the shared predicate model.

Why separate:

Result predicates apply after grouping, so they often compile to `HAVING` or
outer-query `WHERE` conditions.

Work:

- Fold semantic-draft `result_filters` into shared result predicate trees.
- Represent richer `result_predicate` drafts as predicate trees over resolved
  result fields.
- Validate result predicates against selected metrics, executable auxiliary
  metrics, and public measure attributes.
- Compile result predicates into the post-group SQL layer using grouped CTE
  aliases / outer `WHERE` conditions.
- Keep row predicates and result predicates visibly separate in debug output,
  execution plans, runtime payloads, and `Interpreted as:`.

Done when:

- Aggregate/result constraints can use the same predicate language.
- The system does not confuse row-level filters with grouped-result filters.
- `OR`, `NOT`, `IN`, and `BETWEEN` result logic is preserved in plan metadata
  and answer interpretation.

Current boundary:

- Comparison result predicates are still intentionally unsupported because
  comparison results are computed in Python after SQL execution. That belongs
  to a later post-analysis predicate slice, not this SQL post-group slice.

Example acceptance questions:

- `Teams with average points between 110 and 120`
- `Players averaging over 30 minutes and over 20 points`
- `Teams not averaging under 100 points`

## Slice 5: Predicate Presentation And Observability

Status: complete.

Purpose:

Make predicate decisions visible and explainable.

Work:

- Add predicate metadata to execution plans.
- Add predicate metadata to runtime result payloads.
- Update `Interpreted as:` to describe predicate trees clearly.
- Improve debug output so it shows:
  - raw draft predicate
  - grounded IR predicate
  - resolved predicate columns / paths
  - resolved ontology paths
  - compiled SQL predicate
  - execution-plan predicate metadata

Done when:

- A failed or surprising predicate can be debugged without guessing.
- User-facing interpretation explains richer filter logic clearly.

Example interpretation:

```text
Interpreted as: Players ranked by average points where team is Lakers or
Warriors, over the 2025-26 regular season.
```

## Slice 5.5: Predicate Convergence

Status: complete.

Purpose:

Make the shared predicate trees the canonical execution and presentation path
before deleting compatibility structures.

Work completed:

- Semantic draft grounding now folds simple `filters` into `rowPredicate`.
- Semantic draft grounding now folds simple `result_filters` into
  `resultPredicate`.
- Find draft grounding now folds simple find filters into `findPredicateTree`.
- Flat execution-plan and resolved-query predicate structures are no longer
  emitted.
- Resolver code consumes canonical predicate trees directly.
- `Interpreted as:` now prefers predicate trees, with natural parentheses for
  nested boolean logic.

Done when:

- SQL and answer interpretation use predicate trees as the source of truth.
- Tests prove canonical predicate behavior.

## Slice 6: Cleanup

Status: complete.

Purpose:

Remove stale duplicate predicate paths after the shared model is proven.

Work:

- Remove unused flat predicate plumbing.
- Remove duplicate rendering helpers.
- Remove stale tests that only prove old shape details.
- Update docs to describe the new predicate model as the source of truth.

Done when:

- Predicate behavior has one primary model.
- Old flat execution structures are removed rather than preserved as a second
  way to express the same thing.
- The codebase is easier for future agents to navigate.

## Risks

Join aliasing:

Predicate trees may reference multiple ontology paths. SQL compilation must
reuse joins safely and preserve aliases.

Parentheses:

`AND`, `OR`, and `NOT` must compile with correct grouping.

Type safety:

`contains` should not apply to numeric fields. `between` should require two
comparable values. `in` should require a non-empty compatible list.

Value canonicalization:

Aliases such as `LAL`, `Los Angeles Lakers`, `Western`, and `west` need to work
for scalar and list values.

Result placement:

The system must not compile aggregate/result predicates into row-level `WHERE`
clauses when they belong after grouping.

## Recommended Order

The safest order is:

1. Predicate Contract
2. Find Predicate Migration
3. Row Predicate Migration
4. Result Predicate Migration
5. Predicate Presentation And Observability
6. Cleanup

This order gives us working vertical slices while avoiding a big-bang rewrite.
