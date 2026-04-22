# Batch 39

## Decision

Rename five `TeamGame` fields to match the clearer `PlayerGame` naming pattern:

- `game_datetime_utc` -> `game_start_time_utc`
- `minutes_played_decimal` -> `minutes_played`
- `points_fast_break` -> `fast_break_points`
- `points_in_the_paint` -> `points_in_paint`
- `points_second_chance` -> `second_chance_points`

## Why

- the same semantic concepts should use the same public names across `PlayerGame` and `TeamGame`
- the renamed fields read more naturally in prompts
- this removes avoidable inconsistency from the game-level box score surfaces

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- semantic gold tests
- generated semantic artifacts
- live `semantic_gold.team_game`
