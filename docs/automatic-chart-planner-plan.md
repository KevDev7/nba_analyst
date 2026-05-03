# Automatic Chart Planner Plan

## Goal

Automatically include a chart artifact whenever a grounded answer has a clean chartable data profile. Keep the table artifact alongside the chart for exact values and auditability. If the answer cannot be represented as a useful chart, render the answer and table only.

This should remove the need for users to ask "as a chart" while avoiding forced or misleading visualizations.

## Product Decisions

- Charts should appear automatically for supported answers when the result shape is naturally chartable.
- Tables should always remain visible when a table exists.
- Do not create filler charts. If the available result shape has no appropriate quantitative, temporal, or categorical visual encoding, skip the chart.
- The schema and typed answer/table contracts are the safety boundary. The planner should not add phrase-specific restrictions above that boundary.

## Current Behavior

The current chart path runs after answer synthesis:

```text
question -> FinalAnswer -> table artifact -> optional chart artifact
```

Charts are currently limited by two gates:

- The user must explicitly mention chart intent with words like `chart`, `plot`, `graph`, or `visualize`.
- The answer must have `result_shape == "time_series"`.

When both gates pass, the system builds a full, uncapped table artifact from the typed answer rows and always creates a `line_chart`.

The table projection layer already supports all major result shapes:

- `time_series`
- `ranking`
- `aggregate`
- `comparison`
- `object_rows`
- `find_rows`

That means chart planning should happen from the typed `FinalAnswer` plus the full primary table artifact, not from prompt phrases alone.

## Proposed Architecture

Introduce a small chart planner between table projection and `AnalysisTools`.

```text
FinalAnswer + full table artifact
  -> ChartProfile
  -> ChartPlan
  -> AnalysisRequest
  -> ChartArtifact
```

### ChartProfile

`ChartProfile` should describe what is actually available to chart:

- `result_shape`
- date/time columns
- numeric metric columns
- text/category columns
- grouping columns
- row count
- category count
- series count
- whether the answer is ranked
- whether a comparison has time breakdown rows
- primary metric and metric order direction

The planner should choose by visual task, not by preserving coverage for a
particular chart kind:

- time/order progression -> line chart
- one numeric measure across entities/categories -> bar chart
- two meaningful numeric measures per row -> point/scatter chart
- mostly textual records without a clear visual encoding -> table only

### ChartPlan

`ChartPlan` should choose one supported chart template and the fields needed to render it:

- chart kind
- x field
- y field
- optional series/color field
- optional orientation
- optional sort
- title
- metadata explaining the source profile

The planner should return `None` when no clean chart exists.

## Initial Chart Catalog

Keep the first catalog intentionally small and high-quality.

### Time Series

Use for:

- `time_series` results with date/time x and numeric y.
- Time-bucketed comparison results.

Chart:

- line chart
- multi-series line chart when grouping/series exists

### Ranking

Use for:

- `ranking` results where the user primarily wants entities ordered by one
  measure, even if extra display metrics are present.

Chart:

- horizontal bar chart
- entity/category axis against the primary metric
- preserve metric order direction when possible

### Aggregate

Use for:

- `aggregate` results with one clear grouping/category column and one numeric metric.
- `aggregate` results with two meaningful display metrics.

Chart:

- bar chart
- point/scatter chart for metric-vs-metric relationships
- grouped/color bar later if there are multiple grouping columns
- line chart if the grouping is a time bucket

### Comparison

Use for:

- comparison summaries
- comparison breakdown rows

Chart:

- entity comparison: bar chart
- time-bucketed comparison: line chart
- categorical breakdown comparison: grouped bar chart in a later slice

### Object Rows

Use for:

- `object_rows` where rows represent entities and include a numeric metric.
- `object_rows` where rows represent entities and include two or more user-requested metrics.

Chart:

- bar chart over entity/category and primary metric
- point/scatter chart for the first two user-requested metrics, with the table and tooltip preserving the remaining metrics

### Find Rows

Use only when the table columns naturally support a chart:

- date/time + numeric: line or point chart
- two numeric fields per row: point/scatter chart
- category + numeric: bar chart

Skip charts for find results that are mostly record listings with no clear numeric measure. Do not invent count charts for now.

## Implementation Slices

The work should separate behavior-preserving architecture prep from product behavior changes. Cleanup slices should not quietly add new chart coverage, and feature slices should not hide broad refactors.

### Slice 0: Architecture Prep, No Behavior Expansion

Add a chart planner module and move current time-series logic behind it without changing the visible behavior yet.

Expected behavior:

- Explicit chart request for `time_series` still produces the same line chart.
- Non-time-series answers still do not get charts in this slice.
- Questions without chart words still do not get charts.
- The visible artifact order stays the same.

Architecture changes:

- Extract planner-owned `ChartProfile` and `ChartPlan` types.
- Move current time-series field selection out of `chart_artifacts.py`.
- Keep `chart_artifacts.py` as a bridge that builds the full table, asks the planner, calls `AnalysisTools`, and inserts chart artifacts.
- Optionally add backward-compatible `ChartOperation` fields only if they do not change emitted specs or visible behavior.

Likely files:

- `apps/assistant/chart_artifacts.py`
- new `apps/assistant/chart_planner.py`
- `tests/test_chart_artifacts.py`
- new `tests/test_chart_planner.py`
- optionally `services/runtime-py/runtime/AnalysisTools/models.py`
- optionally `tests/test_analysis_tool_contract.py`

Verification:

- Existing chart artifact tests stay green.
- New planner tests cover profile extraction and the current time-series plan.
- Tests should prove this slice is behavior-preserving.

### Slice 1: Ranking and Object Row Bar Charts

Enable charts for ranking and object-row result shapes that have a category/entity column and a numeric metric.

Expected behavior:

- Explicit chart requests for ranking answers get horizontal bar charts.
- Explicit chart requests for object-row metric answers get bar charts.
- Tables remain present.
- Questions without chart words still do not get charts until Slice 4.

Architecture changes:

- Deepen the controlled chart operation contract for bar orientation and sorting.
- Allow true horizontal bars without relying on metadata hacks.
- Preserve grounded answer order where possible, especially for rankings.

Likely files:

- `apps/assistant/chart_planner.py`
- `apps/assistant/chart_artifacts.py`
- `services/runtime-py/runtime/AnalysisTools/models.py`
- `services/runtime-py/runtime/AnalysisTools/operations.py`
- `tests/test_chart_planner.py`
- `tests/test_chart_artifacts.py`
- `tests/test_local_analysis_worker.py`

Verification:

- Ranking chart test.
- Object-row chart test.
- Analysis worker test for horizontal/ordered bar behavior.
- Regression test showing non-chart requests remain unchanged.

### Slice 2: Aggregate and Comparison Charts

Add chart plans for aggregate and comparison result shapes.

Expected behavior:

- Explicit chart requests for aggregate category results get bar charts.
- Explicit chart requests for comparison entity summaries get bar charts.
- Explicit chart requests for time-bucketed comparison breakdowns get line charts.
- Questions without chart words still do not get charts until Slice 4.

Likely files:

- `apps/assistant/chart_planner.py`
- `tests/test_chart_planner.py`
- `tests/test_chart_artifacts.py`

Verification:

- Aggregate table with one grouping column produces a bar chart.
- Entity comparison produces a bar chart.
- Comparison breakdown with `time_bucket` produces a line chart.
- Regression test showing non-chart requests remain unchanged.

### Slice 3: Conservative Find-Row Charts

Add chart plans for `find_rows` only when columns clearly imply a chart.

Expected behavior:

- Explicit chart requests for find rows with date/time and numeric columns can produce a line or point chart.
- Explicit chart requests for find rows with category and numeric columns can produce a bar chart.
- Find rows with no useful numeric measure remain table-only.
- No count charts are invented in this slice.
- Questions without chart words still do not get charts until Slice 4.

Likely files:

- `apps/assistant/chart_planner.py`
- `tests/test_chart_planner.py`
- `tests/test_chart_artifacts.py`

Verification:

- Date + numeric find rows produce a chart.
- Category + numeric find rows produce a chart.
- Text-only find rows produce no chart.
- Regression test showing non-chart requests remain unchanged.

### Slice 4: Automatic Chart Generation

Remove the prompt-word chart gate and let the planner decide.

Expected behavior:

- Users no longer need to say "as a chart".
- Any chartable supported answer includes a chart.
- Non-chartable answers remain answer + table only.

Likely files:

- `apps/assistant/chart_artifacts.py`
- `tests/test_chart_artifacts.py`
- `tests/test_web_api.py` if API snapshots assert artifact shape

Verification:

- Time-series question without chart words includes chart + table.
- Ranking question without chart words includes chart + table.
- Non-chartable find question includes table only.
- Existing explicit chart requests still work.

### Slice 5: Layout and Coverage Polish

Harden presentation after broader chart coverage exists.

Expected behavior:

- Dense legends remain readable across chart types.
- Horizontal bars have enough height and sensible label behavior.
- Mobile chart rendering remains usable.
- Chart metadata is stable enough for frontend layout policy without parsing Vega internals.

Likely files:

- `apps/web-ui/src/lib/charts/chartLayout.ts`
- `apps/web-ui/src/lib/charts/chartLayout.test.ts`
- `apps/web-ui/src/lib/artifacts/ChartArtifact.svelte`
- `services/runtime-py/runtime/AnalysisTools/models.py` if chart metadata needs to be typed more explicitly

Verification:

- Frontend chart layout tests cover line, vertical bar, horizontal bar, and many-series charts.
- Browser smoke check on representative chart answers.

## Open Risks

- Horizontal bar charts now allow categorical y and numeric x through the controlled operation contract.
- Sorting preserves grounded ranking order when the table includes rank.
- Point/scatter charts use the first two user-requested display metrics as axes. This is grounded in semantic draft order, but a future planner may use richer metric-role hints such as independent/dependent measure.
- Grouped/multi-metric bars are still not implemented, so some comparison breakdowns remain table-only or use the best simpler chart.
- High-cardinality category charts can become noisy. The first planner should avoid inventing truncation above the answer contract, but the UI may need responsive layout policies for dense charts.

## Confidence

High. The existing typed answer and table projection contracts already provide most of the needed structure. The work is now split into one behavior-preserving architecture slice, four behavior-expansion slices, and one polish slice.
