# Batch 41

## Decision

Add two high-value game context fields to `PlayerGame`:

- `opponent_team_id`
- `game_result`

## Why

- both are common player-game query dimensions
- they support direct questions like player stats against an opponent or in wins vs losses
- they are justified context duplication from the game/team-game layer

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- semantic gold tests
- generated semantic artifacts
- live `semantic_gold.player_game`
