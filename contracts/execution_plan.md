# Execution Plan Contract

This file describes the live runtime plan contract.

## Required Fields

- `plan_type`
- `query_kind`
- `result_shape`
- `metric`
- `window_games`
- `limit`
- `assumptions`
- `steps`

## Live Shapes

- `single_sql`
  - ranking over `total_points`
  - ranking over `average_points`
  - object rows with attached `total_points`
- `multi_step`
  - SQL + Python comparison over `total_points`

## Important Contract Point

The runtime now needs to know which governed metric the plan resolved, not just which SQL text to execute.
