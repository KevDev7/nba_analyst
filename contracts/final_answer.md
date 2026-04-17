# Final Answer Contract

This file describes the live final-answer payload contract.

## Required Fields

- `summary`
- `metric`
- `window_games`
- `limit`
- `assumptions`

## Result Payloads

Ranking answers include:

- `rows`
  - `rank`
  - `player_name`
  - `team`
  - `metric_value`

Object answers include:

- `object_rows`
  - `entity_id`
  - `player_name`
  - `team`
  - `metric_value`

Comparison answers include:

- `comparison`
  - leader
  - point differential
  - per-player totals and averages
