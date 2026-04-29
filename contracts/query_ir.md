# Query IR Contract

This file describes the live query IR contract shared across the semantic core.

## Query Root

- `Query = ObjectQuery | MetricQuery | FindQuery`

## Shared Base Fields

- `coreFactObject`
- `metrics`
- `dimensions`
- `filters`
- `orders`
- `limit`
- `assumptions`
- row predicate tree
- result predicate tree
- optional time grain

`FindQuery` uses a dedicated row-retrieval shape with display dimensions,
ontology-grounded find orders, time filters, and the shared predicate-tree
contract.

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

Find rows:

```text
FindQuery
  { targetObject = Game
  , displayDimensions = [GameDate, TeamName, Score]
  , findOrders = [Desc GameDate]
  , findPredicateTree =
      And
        [ Team = Lakers
        , Score > 120
        ]
  , findFilters = [LastNGames 10]
  , limit = Nothing
  }
```
