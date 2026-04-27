# Query Path: Top-N Ranking

This doc shows one live path through the architecture for the total-points Top-N ranking query.

Question:

- `Show me the top 10 players by points over the last 10 games`

## 1. Ontology Layer

The ontology provides:

- object: `PlayerGame`
- dimension: `full_name`
- measure: `points`
- metric: `total_points`

## 2. Query Model

The query model interprets the question as:

- query type: `MetricQuery`
- core fact object: `PlayerGame`
- metric: `total_points`
- dimension: `full_name`
- filter: `LastNGames 10`
- order: descending by `total_points`
- limit: `10`

## 3. Grounded Planning

The planner validates the IR and compiles it into a SQL query over `player_game`.

The SQL uses a per-player recent-games window and ranks players by total points.

## 4. Analysis Runtime

The runtime executes the SQL in DuckDB and returns the ranked rows.

## 5. Answer Synthesis

The answer layer formats:

- a short summary sentence
- a ranked results table
