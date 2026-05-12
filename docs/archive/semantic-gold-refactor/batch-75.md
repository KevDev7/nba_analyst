# Batch 75

Removed double-double and triple-double fields from `semantic_gold`.

## Removed

- `semantic_gold.player_game.is_double_double`
- `semantic_gold.player_game.is_triple_double`
- `semantic_gold.player_season.double_doubles`
- `semantic_gold.player_season.triple_doubles`

## Why

These fields were no longer wanted in the public semantic surface.

## Scope

This batch removes them from:

- schema contracts
- semantic transforms
- attribute inventory
- semantic tests
- generated ontology/interpreter artifacts
