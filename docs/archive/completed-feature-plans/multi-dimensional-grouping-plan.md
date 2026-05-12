# Multi-Dimensional Grouping Plan

## Product Goal

Users should be able to ask grouped analytics questions with more than one
business grouping dimension.

Examples:

- `average points by team and season`
- `wins by team and season type`
- `average points by conference and season type`
- `points by player and month`

This is a normal analytics capability, not an exotic SQL trick. The important
part is to add it through the existing grounded pipeline:

```text
natural language
-> semantic draft
-> typed query IR
-> ontology validation/resolution
-> execution plan
-> SQL/runtime
-> answer formatting
```

Do not solve this by adding freeform SQL generation.

## Historical Starting Limitation

This was the limitation before the multi-dimensional grouping slices.

The IR already represented dimensions as a list, but the implemented planner
mostly assumed exactly one displayed/grouped dimension.

The old assumptions appeared in several layers:

- semantic draft grounding rejects aggregate drafts with more than one grouping
  dimension
- validation requires exactly one business grouping dimension for ranking,
  aggregation, and comparison shapes
- resolution returns one row object/path/display column
- SQL compilers emit one `entity_name`
- runtime result models expose one `entity_name` plus optional `context_value`
- answer formatting assumes one entity column plus optional context column

This is why the implementation did not simply remove the `exactly one
dimension` checks. It added explicit grouped-dimension structures across
grounding, validation, resolution, SQL compilation, runtime models, and answer
formatting.

## Design Principle

Multi-dimensional grouping should be represented as intentional grouped output,
not as accidental metadata columns.

The system should distinguish:

- grouping dimensions: fields that define result row grain
- identity/context metadata: useful extra columns about the grouped entities
- metric/result columns: computed measurements

The schema contract remains the safety boundary. A grouped dimension is valid
only if the ontology can resolve it from the selected fact object through a safe
path.

## Slice 1: Aggregate Multi-Dimensional Grouping

Purpose:

Support aggregate questions where the result row is defined by multiple
grouping dimensions.

Status: implemented for aggregate queries.

Example questions:

- `average points by team and season type`
- `wins by team and season type in the 2025-26 season`
- `average points by conference and season type`

Expected behavior:

```text
Team | Season Type | Average Points
--- | --- | ---
Lakers | Regular Season | ...
Lakers | Playoffs | ...
```

Likely implementation:

- Add a resolved grouping-dimension structure that can hold multiple grouped
  fields.
- Allow aggregate semantic grounding to resolve more than one dimension.
- Validate each grouping dimension against the ontology and the selected fact
  object.
- Compile aggregate SQL with multiple selected grouping columns and `GROUP BY`
  all grouping columns.
- Add runtime/result support for generic grouping display values.
- Format aggregate rows with grouping columns before metric columns.

Done when:

- Aggregate queries can group by two or more valid ontology dimensions.
- SQL groups by the same fields shown in the answer table.
- Existing one-dimensional aggregate behavior still works.
- Invalid dimensions fail because the ontology cannot resolve them, not because
  of an artificial one-dimension planner restriction.

## Slice 2: Ranking And Object Multi-Dimensional Display Context

Purpose:

Extend grouping/display behavior carefully to ranking and object-style
questions.

Status: implemented for grouped ranking queries. Object queries intentionally
keep one-row-per-object semantics; grouped metric intent should route to rank or
aggregate instead of mutating object rows.

Example questions:

- `rank teams by wins by season type`
- `show players and total points by team and season`

Why this is harder:

- Ranking with multiple dimensions ranks groups, not just entities.
- Object queries are supposed to be one row per business object, so adding
  grouping dimensions can blur object rows into aggregate rows.

Likely implementation:

- Decide when ranking dimensions define grouped rank grain versus display
  metadata.
- Preserve one-row-per-object semantics for object queries unless the user asks
  for grouped metrics.
- Reuse the grouping-dimension structures from Slice 1 where the semantics are
  genuinely grouped.
- Keep rank ordering explicit and deterministic across grouped rows.

Done when:

- Ranking grouped by multiple dimensions is supported where the semantics are
  clear.
- Object queries do not silently become aggregates unless the query family
  grounding makes that explicit.
- Existing ranking/object behavior remains stable.

## Slice 3: Trend Multi-Dimensional Grouping

Purpose:

Support trend questions where the result grain is a time bucket plus one or
more ontology-backed grouping dimensions.

Status: implemented for trend queries.

Example questions:

- `trend points by player and month`
- `trend points and assists by team and month`
- `monthly wins by team and season type`

Why this is delicate:

- Trend already has a time grain, which is itself a grouping axis.
- Time grain and business grouping dimensions are different concepts.
- The answer shape should not blur `month`/`week`/`season` with grouped entity
  columns like `team`, `player`, `conference`, or `season type`.

Likely implementation:

- Treat time grain and grouping dimensions as separate concepts.
- Reuse grouped dimension structures only when they preserve clear result
  grain.
- Allow multi-series trend output where the ontology supports it.
- Keep SQL output explicit: one time bucket column, then grouping columns, then
  metric/result columns.

Done when:

- Trend can safely combine time grain with one or more valid grouping
  dimensions.
- Time grain remains distinct from business grouping dimensions in IR,
  execution plans, and formatted output.
- Existing single-series and one-series trend behavior remains stable.

## Slice 4: Compare Grouped Breakdowns

Purpose:

Support comparison questions where each compared entity can be broken down by a
valid grouping dimension.

Status: implemented for comparison breakdowns by ontology-backed grouping
dimensions and calendar time grains.

Example questions:

- `compare Brunson and Tatum by season type`
- `compare Lakers and Warriors by month`
- `compare Curry and LeBron by regular season vs playoffs`

Why this is delicate:

- Compare already has comparison entities as a grouping axis.
- Grouped compare may need staged SQL plus Python reshaping/summary instead of
  one larger SQL query.
- The answer needs to stay understandable: each row or section should make clear
  which entity, time/group bucket, and metric value is being compared.

Likely implementation:

- Keep comparison entities as the primary comparison axis.
- Add grouped breakdown dimensions only when the ontology can resolve them from
  the selected fact object.
- Prefer SQL for grounded metric extraction and Python for comparison
  summarization when the result shape becomes multi-step.
- Preserve ungrouped comparison behavior.

Done when:

- Comparison can support grouped breakdowns only when the answer shape remains
  understandable.
- Runtime output carries enough structure for synthesis to explain each
  compared entity and grouping bucket.
- The execution plan can still choose SQL-only or SQL-plus-Python based on the
  analytical work required.

Current behavior:

- Comparison entities remain the primary axis.
- Business breakdown dimensions are carried as grouping columns.
- Calendar grains such as month are carried separately as time buckets.
- Python comparison analysis computes both the overall comparison and grouped
  breakdown rows for answer synthesis.

## Recommended Order

1. Aggregate Multi-Dimensional Grouping
2. Ranking And Object Multi-Dimensional Display Context
3. Trend Multi-Dimensional Grouping
4. Compare Grouped Breakdowns

This order starts with the cleanest SQL/reporting shape, then expands into the
more ambiguous families after the shared grouping model is proven.
