# Final Answer Contract

This file describes the live final-answer payload contract.

## Required Fields

- `summary`
- `interpretation`
- `query_kind`
- `result_shape`
- `metric`
- `window_games`
- `limit`
- `assumptions`

## Result Payloads

Ranking answers include:

- `rows`
  - `rank`
  - `entity_name`
  - optional context/group/display values
  - `metric_value`

Aggregate answers include:

- `aggregate_rows`
  - `entity_name`
  - optional group/display values
  - `metric_value`

Object answers include:

- `object_rows`
  - `entity_id`
  - `entity_name`
  - optional context/display values
  - `metric_value`

Find answers include:

- `find_rows`
  - user-requested or planner-selected display columns
  - predicate-context columns when useful
- `find_orders`
  - grounded sort fields and directions when the user requested ordering

Trend answers include:

- `time_series_rows`
  - `time_bucket`
  - optional series/group values
  - `metric_value`

Comparison answers include:

- `comparison`
  - leader
  - metric differential
  - per-entity metric values
  - per-entity `display_values` when multiple metrics are shown
  - optional grouped breakdown rows

Single-metric comparison can use leader/differential prose. Multi-metric
comparison should render one row per compared entity and one column per metric,
because unrelated metrics should not be collapsed into one overall winner.
