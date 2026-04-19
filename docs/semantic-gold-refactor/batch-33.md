# Batch 33

## Decision

Rename the shared home/away context field on:

- `PlayerGame`
- `TeamGame`

from:

- `team_side`

to:

- `team_home_or_away`

## Why

- `team_side` is understandable once you know the schema, but it is still a little abstract
- `team_home_or_away` says exactly what the field means in more human language
- this should make prompt interpretation and query generation a bit clearer

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_game_parquet.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- generated semantic artifacts
- live `semantic_gold.player_game`
- live `semantic_gold.team_game`

## Notes

- this is a public semantic rename only
- the lower-layer source field can still remain `team_side`
