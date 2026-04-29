# Query Model

This doc pins down the current live query model for the one-step NBA analyst.
It describes what the Haskell semantic core accepts after the LLM produces a
loose semantic draft and before grounded planning validates/compiles it.

## Top-Level Shape

The query root is:

- `Query = ObjectQuery | MetricQuery | FindQuery`

All three variants are live.

## Shared Base Shape

`ObjectQuery` and `MetricQuery` share:

- `coreFactObject`
- `metrics`
- `dimensions`
- `filters`
- `orders`
- `limit`
- `assumptions`

They also carry newer shared semantic fields where needed:

- row predicate tree
- result predicate tree
- optional time grain

`FindQuery` has its own shape because it returns matching rows instead of a
metric result, but it uses the same predicate-tree contract for grounded row
filters.

## Live Families

### `MetricQuery`

Supported examples:

- `Show me the top 10 players by points over the last 10 games`
- `Compare Brunson and Haliburton scoring over the last 10 games`
- `Show me players by average points over the last 10 games`
- `Calculate average points by team and season type over the last 10 games`
- `Trend average points by team and season type by month over the past year`
- `Compare Lakers and Warriors average points by month over the past year`

Important current distinctions:

- raw measure language like `points` maps to the governed metric `total_points`
- governed metric language like `average points`, `avg points`, or `average scoring` maps to `average_points`
- rank/object/aggregate can carry extra display metrics, while trend and
  comparison still currently use one selected metric
- dimensions are a list and can represent grouped output grain, not just one
  display column

### `ObjectQuery`

Supported examples:

- `Show me players and their total points over the last 10 games`
- `Show me players with their scoring totals over the last 10 games`
- `Show me the top 5 players and their total points for the Knicks over the last 10 games`
- `Show me players with points, rebounds, and assists over the last 10 games`

Important idea:

- each row represents one business object, usually a player or team
- attached metrics can still be computed from linked fact rows
- object rows can carry a limit/order; `and their` / `with their` keeps the
  family as `ObjectQuery`, while `by <measure>` belongs to ranking

### `FindQuery`

Supported examples:

- `Find Lakers games where score is over 120`
- `Find teams not in the West`
- `Find players whose name contains Smith`
- `Find Lakers or Warriors games between Jan 1 2025 and Feb 1 2025`

Important idea:

- find queries are row-retrieval questions, not metric summaries
- display columns can come from user display intent when they resolve to public
  ontology-backed fields
- order intent can sort by public ontology-backed fields, including linked
  fields such as `opponent`
- row predicates use the shared predicate tree: `and`, `or`, `not`, `in`,
  `not_in`, `between`, and `contains`

## Current Restrictions

The query model is no longer limited to points-only, last-N-games-only,
player-only, or two hardcoded comparison players. The remaining restrictions
are current result-shape/runtime limits:

- trend and comparison still require one selected metric
- comparison result predicates are not supported yet because comparison deltas
  are computed after SQL execution
- trend supports day/week/month/season grains, but not last-N-games as a trend
  time scope yet
