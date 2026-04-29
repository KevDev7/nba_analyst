# Execution Plan Contract

This file describes the live runtime plan contract.

## Required Fields

- `plan_type`
- `query_kind`
- `result_shape`
- `entity_label_singular`
- `entity_label_plural`
- `metric`
- `window_games`
- time scope metadata when present
- `limit`
- `assumptions`
- predicate/grouping/display metadata when present
- find order metadata when present
- `steps`

## Live Shapes

- `single_sql`
  - ranking/top-N
  - grouped aggregates
  - object rows
  - find rows
  - time-series trends
- `multi_step`
  - SQL + Python comparison summaries and grouped comparison breakdowns

## Important Contract Point

The runtime needs more than SQL text. It needs the governed metric, result
shape, time scope, predicates, grouping columns, display metadata, assumptions,
and executable steps so answer synthesis can stay grounded in the plan.

When `display_metrics` is present, each item includes:

- `column_key`
- `metric`
- `label`
- `aggregation`

The `aggregation` field lets Python runtime aggregate each displayed metric
independently, which is required for multi-metric comparison.

For Find plans, `find_orders` carries user-requested grounded ordering as:

- `order_field`
- `order_direction`

This lets answer synthesis disclose sort intent without parsing SQL.
