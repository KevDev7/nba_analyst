# Batch 37

## Decision

Remove these historical bookkeeping fields from `Team`:

- `first_seen_game_date`
- `last_seen_game_date`

## Why

- both are derivable
- both are low-frequency compared with the rest of the team object
- they add historical bookkeeping more than core team semantics

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- generated semantic artifacts
- live `semantic_gold.team`
