# Batch 74

Removed `assist_ratio` and `turnover_ratio` from the semantic player/team season tables.

## Removed

- `semantic_gold.player_season.assist_ratio`
- `semantic_gold.player_season.turnover_ratio`
- `semantic_gold.team_season.assist_ratio`
- `semantic_gold.team_season.turnover_ratio`

## Why

These two fields were no longer desired in the public semantic surface.

This batch removes them from:

- schema contracts
- semantic transforms
- attribute inventory
- tests
- generated ontology/interpreter artifacts
