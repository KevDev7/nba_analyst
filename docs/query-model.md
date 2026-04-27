# Query Model

This doc pins down the live query model after slice 4.

## Top-Level Shape

The query root is:

- `Query = ObjectQuery | MetricQuery`

Both variants are live.

## Shared Base Shape

Both query kinds share:

- `coreFactObject`
- `metrics`
- `dimensions`
- `filters`
- `orders`
- `limit`
- `assumptions`

## Live Families

### `MetricQuery`

Supported examples:

- `Show me the top 10 players by points over the last 10 games`
- `Compare Brunson and Haliburton scoring over the last 10 games`
- `Show me players by average points over the last 10 games`

Important current distinction:

- raw measure language like `points` maps to the governed metric `total_points`
- governed metric language like `average points`, `avg points`, or `average scoring` maps to `average_points`

### `ObjectQuery`

Supported example:

- `Show me players and their total points over the last 10 games`
- `Show me players with their scoring totals over the last 10 games`
- `Show me the top 5 players and their total points for the Knicks over the last 10 games`

Important idea:

- each row is a `Player`
- the attached metric is still computed from linked `PlayerGame` rows
- object rows can carry a limit/order; `and their` / `with their` keeps the
  family as `ObjectQuery`, while `by <measure>` belongs to ranking

## Current Narrowness

The architecture is now aligned, but the supported language remains intentionally narrow:

- points-focused metrics only
- `last N games` only
- player-centric output only
- comparison only for Brunson and Haliburton
