# Family Ontology-Backed Standard

This doc records the standard we decided to hold the six explicitly supported
query families to after the family cleanup slices.

The goal is to stop the endless loop of reopening families for smaller and
smaller purity fixes, while still holding a high bar for ontology-backed
behavior.

## Why This Standard Exists

We have spent multiple slices removing fake family restrictions:

- player-only comparison
- `team_name`-only linked filters
- hardcoded metric and dimension enums above the ontology
- fixed capability lists that were not derived from planner truth

That work was valuable, but it also risked turning into a repetitive cleanup
loop where every family is always "almost done" but never actually considered
done.

So we need a concrete stopping rule.

## The Standard

A family is considered "ontology-backed enough for this phase" if all of the
following are true:

1. Core semantic references are ontology-backed.
   - Metrics, dimensions, target objects, linked objects, and identity
     dimensions come from ontology truth rather than handwritten bless-lists.

2. Support is not primarily gated by a narrow handcrafted allowlist.
   - The family is not mainly limited by one blessed object, one blessed
     dimension, one blessed metric, or one special-case attribute path.

3. Capability derivation is driven by planner truth.
   - Supported capability families come from validation, resolution, and
     compilation truth rather than a manually curated family matrix.

4. Remaining restrictions are explainable as current runtime or result-shape
   truth.
   - If a restriction remains, we can explain what failure it prevents and why
     it is still needed for the current execution or answer-shape path.

5. The interpreter is not secretly redefining the family.
   - The interpreter may map language into the contract, but it should not be
     the hidden source of what the family supports.

## What This Standard Is Not

This is not the same as "fully ontology-backed in the ideal long-term sense."

A family can pass this standard and still have:

- one-metric limits
- one-dimension limits
- path-depth limits
- runtime-specific shape limits
- family-specific time or cardinality limits

The point of the standard is not perfection. The point is to distinguish:

- fake restrictions caused by handwritten family boxes

from:

- honest restrictions caused by current planner, runtime, or answer-shape
  limits

## The Six Explicitly Supported Families

For the current repo, the six explicit supported families are:

1. ranking / top-N
2. aggregation
3. filtering / joining
4. trend
5. comparison
6. object rows

## Current Assessment

Under the standard above, all six families now count as done for this phase.

### 1. Ranking / Top-N

Status: passes

Why it passes:

- metrics and dimensions are now ontology-backed
- capability derivation is planner-derived
- linked-filter support is ontology-reachable rather than tied to a tiny
  handwritten set
- row-level numeric predicates and aggregate/result predicates are separated
  instead of forcing both meanings through the same filter lane

What still falls short of full ontology-backed behavior:

- ordering is still centered on a primary selected metric
- limited limit behavior

### 2. Aggregation

Status: passes

Why it passes:

- core metric and dimension references are ontology-backed
- support is no longer mainly driven by handwritten metric or dimension lists
- capability derivation comes from validate + resolve + compile truth
- aggregate/result predicates are supported for selected metrics and explicit
  auxiliary aggregates such as average minutes

What still falls short of full ontology-backed behavior:

- current answer and result shapes are still centered on grouped metric tables

### 3. Filtering / Joining

Status: passes

Why it passes:

- filters are text-backed rather than enum-blocked
- linked-filter support is now based on ontology reachability and public
- dimension or numeric-measure truth
- capability derivation is no longer tied to one special linked target shape

What still falls short of full ontology-backed behavior:

- ordinary queries now share a broader `TimeScope` contract for recent games,
  last-N-days, past year, date ranges, all available data, and exact seasons
- multiple linked filters are supported when each filter has a valid ontology
  path to a public dimension or numeric measure
- path traversal is still capped at depth 2

### 4. Trend

Status: passes, but is the most borderline family

Why it passes:

- fact-surface and grouping support are no longer hardcoded to one fact object
  and one blessed dimension
- grouping uses reachable public dimensions rather than a tiny allowlist
- capability derivation is planner-derived

What still falls short of full ontology-backed behavior:

- trend now separates time grain from time scope, so exact-season trends,
  past-year trends, last-N-days trends, and date-range trends are supported
  when the fact surface exposes the required fields
- trend filters are still calendar/date shaped
- supported grains are day, week, month, and season
- last-N-games trend scopes are still intentionally unsupported until the
  product defines whether that means per-entity recent games, league-wide
  recent game dates, or something else
- linked filters are supported when each filter has a valid ontology path
- aggregate/result predicates are supported on the trend result after grouping
- no explicit ordering
- no limit

Trend is the closest family to the line, but it still passes because the
remaining restrictions look more like current runtime truth than stale
handwritten bless-lists.

### 5. Comparison

Status: passes

Why it passes:

- comparison is no longer player-only
- comparison is no longer tied to one identity dimension or one blessed metric
- comparison target objects and identity dimensions come from ontology truth
- capability derivation is planner-derived

What still falls short of full ontology-backed behavior:

- comparison supports shared metric time scopes, including recent games,
  last-N-days, past year, date ranges, all available data, and exact seasons
- comparisons support two or more distinct resolved entities
- linked filters are supported when each filter has a valid ontology path
- aggregate/result predicates are intentionally rejected because comparison
  deltas are computed after SQL execution
- no explicit ordering
- no limit

### 6. Object Rows

Status: passes

Why it passes:

- object-row questions are now a first-class semantic draft family
- object drafts ground into typed `ObjectQuery` IR instead of masquerading as
  ranking or aggregate questions
- row objects, metrics, identity dimensions, and paths are selected through
  ontology grounding
- runtime and answer synthesis preserve the `object_rows` result shape

What still falls short of full ontology-backed behavior:

- current output is still table-shaped; presentation caps displayed rows at 50
  when the underlying result is larger
- linked filters are supported when each filter has a valid ontology path
- aggregate/result predicates are supported for selected metrics and explicit
  auxiliary aggregates such as average minutes

## Why We Are Moving Forward

We are moving forward because the six families now meet the phase standard.

That means:

- the main fake handwritten family boxes have been removed
- the support surface is now mostly determined by ontology, validation,
  resolution, and compilation truth
- the remaining restrictions are mostly current runtime and result-shape limits
  rather than stale allowlists

At this point, continuing to polish families one by one would likely produce
diminishing returns and repeat the same pattern:

- find a smaller restriction
- loosen it
- discover another smaller restriction
- call the family "almost done" again

That is not the right next architectural phase.

## What Comes Next

The next major architectural gap is not another family cleanup slice.

The bigger remaining move is a richer ontology-driven semantic layer upstream
of IR, something closer to:

- scan
- semantic match
- classify
- build

The project should now shift away from treating family cleanup as the main
workstream and toward that broader semantic-construction phase.

## Practical Rule Going Forward

Do not reopen a family just because it is not fully ontology-backed in the
ideal sense.

Reopen a family only if one of these is true:

- it still fails because of a fake handwritten allowlist
- a restriction cannot be honestly justified as current runtime or answer-shape
  truth
- there is a concrete user-facing product bug caused by stale family logic

Otherwise, treat the family as complete for this phase and move on.
