# Multi-Metric Trend And Compare Plan

## Product Goal

Users should be able to ask trend and comparison questions with more than one
metric without the system silently dropping extra requested metrics.

Examples:

- `Compare Stephen Curry and LeBron James by points, assists, and rebounds over the last 10 games`
- `Trend Lakers points, assists, and rebounds by month over the past year`
- `Compare Brunson and Tatum by points, assists, and rebounds by season type over the last 10 games`

This is not a freeform SQL-generation feature. It should stay inside the
existing grounded pipeline:

```text
natural language
-> semantic draft with multiple measures
-> typed query IR with multiple ontology metrics
-> grounded planning
-> execution plan
-> SQL/Python runtime
-> grounded answer formatting
```

## Current Behavior

The LLM draft schema already has both:

- `measure`
- `measures`

The prompt already tells the LLM to preserve multiple requested measures in
`measures`.

However, trend and compare currently collapse the request to the primary
`measure` during semantic grounding.

That means a question such as:

```text
Compare Curry and LeBron by points, assists, and rebounds over the last 10 games
```

can plan successfully but only execute/display the primary metric, usually
points. Assists and rebounds are silently lost.

## Design Principle

The ontology/schema contract remains the safety boundary.

If the selected fact surface has all requested executable metrics, trend and
compare should preserve them. If one requested metric cannot be grounded against
the selected fact surface, the system should fail clearly because the ontology
cannot support that metric on that surface.

Do not add phrase-specific corridors such as special handling only for
`points, assists, rebounds`.

## Important Semantic Distinction

Multi-metric comparison should not pretend there is always one overall winner.

For one metric:

```text
Brunson led Tatum by 3.2 average points.
```

For multiple metrics:

```text
Player | Points | Assists | Rebounds
--- | --- | --- | ---
Brunson | ... | ... | ...
Tatum | ... | ... | ...
```

Each metric can have its own leader. A summary may mention notable leaders, but
the core answer shape should be side-by-side metric columns.

Trend should remain chronological by default. This feature does not need new
ASC/DESC assumptions; trend ordering should stay time-bucket ascending unless a
separate display/order-control feature changes that later.

## Slice 1: Multi-Metric Trend

Status: implemented.

Purpose:

Support trend questions with multiple requested metrics.

Example questions:

- `Trend points, assists, and rebounds by month over the past year`
- `Trend Lakers points, assists, and rebounds by month over the past year`
- `Trend average points and average assists by team and month over the past year`

Expected behavior:

```text
Month | Points | Assists | Rebounds
--- | --- | --- | ---
2025-01 | ... | ... | ...
2025-02 | ... | ... | ...
```

If grouped by a business dimension:

```text
Month | Team | Points | Assists | Rebounds
--- | --- | --- | --- | ---
2025-01 | Lakers | ... | ... | ...
```

Likely implementation:

- Ground all requested trend measures against the chosen fact object.
- Keep the first measure as the primary `metric` for backward compatibility.
- Carry all requested metric formulas as display metrics.
- Compile trend SQL with one result column per requested metric.
- Extend `TimeSeriesRow` or its display-value path so extra metric columns
  survive runtime packaging.
- Update interpretation, summary, and formatting to show multiple metric
  columns.

Done when:

- Multi-metric trend questions show all requested metrics.
- Existing single-metric trend behavior remains stable.
- Invalid extra metrics fail because they cannot be grounded on the selected
  ontology fact surface.

## Slice 2: Multi-Metric Compare Core

Status: implemented.

Purpose:

Support ungrouped comparison questions with multiple requested metrics.

Example questions:

- `Compare Brunson and Tatum by points, assists, and rebounds over the last 10 games`
- `Compare Lakers and Warriors by wins and average points in the 2025-26 regular season`

Expected behavior:

```text
Player | Points | Assists | Rebounds
--- | --- | --- | ---
Jalen Brunson | ... | ... | ...
Jayson Tatum | ... | ... | ...
```

Likely implementation:

- Ground all requested comparison measures against the chosen fact object.
- Compile comparison SQL with one source/result column per metric.
- Extend Python comparison analysis to aggregate each metric independently.
- Preserve the old single-metric leader/differential behavior when only one
  metric is requested.
- For multiple metrics, use a side-by-side table as the primary answer shape
  instead of forcing one global comparison leader.

Done when:

- Multi-metric compare questions return one row per compared entity and one
  column per metric.
- Single-metric comparison output remains stable.
- Comparison still works for two or more entities.

## Slice 3: Multi-Metric Compare Breakdowns And Hardening

Status: implemented.

Purpose:

Extend multi-metric comparison through grouped/time-bucketed breakdowns and
polish observability/presentation.

Example questions:

- `Compare Brunson and Tatum by points, assists, and rebounds by season type over the last 10 games`
- `Compare Lakers and Warriors by points and assists by month over the past year`

Expected behavior:

```text
Month | Team | Points | Assists
--- | --- | --- | ---
2025-01 | Lakers | ... | ...
2025-01 | Warriors | ... | ...
```

Likely implementation:

- Carry multi-metric comparison values through grouped breakdown rows.
- Update `Interpreted as:` so all requested metrics are visible.
- Update debug output indirectly through execution-plan/display-metric metadata.
- Add regression tests for grouped compare, time-bucketed compare, and
  single-metric compatibility.

Done when:

- Grouped and time-bucketed multi-metric comparison works end-to-end.
- The answer clearly shows entity, grouping/time bucket, and all requested
  metric columns.
- Existing comparison breakdown behavior remains stable for one metric.

## Likely Files To Touch

Semantic draft grounding:

- `services/ontology-hs/src/QueryModel/SemanticConstruction/Build/Trend.hs`
- `services/ontology-hs/src/QueryModel/SemanticConstruction/Build/Compare.hs`
- `services/ontology-hs/src/QueryModel/SemanticDraft/Types.hs`

Grounded planning:

- `services/ontology-hs/src/GroundedPlanning/Validation/Common/Metrics.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Common/Metrics.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Trend.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Compare.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Common/Types.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile/PlanBuilder.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile/Sql/Trend.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile/Sql/Comparison.hs`
- `services/ontology-hs/src/GroundedPlanning/Compile/Sql/Common.hs`

Runtime and answer synthesis:

- `services/runtime-py/runtime/AnalysisRuntime/models.py`
- `services/runtime-py/runtime/AnalysisRuntime/runner.py`
- `services/runtime-py/runtime/AnalysisRuntime/analysis.py`
- `services/runtime-py/runtime/AnswerSynthesis/interpretation_summary.py`
- `services/runtime-py/runtime/AnswerSynthesis/synthesize.py`
- `services/runtime-py/runtime/AnswerSynthesis/format_response.py`

Tests:

- `tests/test_trend_planning.py`
- `tests/test_trend_cli_variants.py`
- `tests/test_comparison_planning.py`
- `tests/test_comparison_cli_variants.py`
- `tests/test_comparison_generic_runtime.py`
- `tests/test_multi_dimensional_grouping.py`

## Verification Plan

Run focused tests after each slice:

```bash
cabal build -v0 ontology-hs
python3 -m pytest tests/test_trend_planning.py tests/test_trend_cli_variants.py -q
python3 -m pytest tests/test_comparison_planning.py tests/test_comparison_cli_variants.py tests/test_comparison_generic_runtime.py -q
python3 -m pytest tests/test_multi_dimensional_grouping.py -q
python3 -m compileall apps/cli apps/assistant services/runtime-py/runtime tests
git diff --check
```

At the end, run:

```bash
python3 -m pytest tests -q
```

## Recommended Order

1. Multi-Metric Trend
2. Multi-Metric Compare Core
3. Multi-Metric Compare Breakdowns And Hardening

Trend comes first because it is SQL-only and can reuse more of the existing
display-metric path. Compare comes next because its Python analysis model is
currently one-metric-shaped and needs a more deliberate answer shape.
