# Batch 40

## Decision

Remove `seconds_played_total` from `TeamGame`.

## Why

- `minutes_played` already carries the useful public semantic value
- second-level precision adds noise for the semantic layer
- this keeps `TeamGame` aligned with the earlier `PlayerGame` cleanup

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- generated semantic artifacts
- live `semantic_gold.team_game`
