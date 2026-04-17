# Query IR Contract

This file describes the live query IR contract shared across the semantic core.

## Query Root

- `Query = ObjectQuery | MetricQuery`

## Shared Base Fields

- `coreFactObject`
- `metrics`
- `dimensions`
- `filters`
- `orders`
- `limit`
- `assumptions`

## Live Examples

Metric ranking:

```text
MetricQuery
  { coreFactObject = PlayerGame
  , metrics = [AveragePoints]
  , dimensions = [PlayerName]
  , filters = [LastNGames 10]
  , orders = [Desc AveragePoints]
  , limit = Nothing
  }
```

Object rows:

```text
ObjectQuery
  { rowObject = Player
  , coreFactObject = PlayerGame
  , metrics = [TotalPoints]
  , dimensions = [PlayerName]
  , filters = [LastNGames 10]
  , orders = [Desc TotalPoints]
  , limit = Nothing
  }
```
