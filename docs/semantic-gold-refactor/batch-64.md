# Batch 64

Added the remaining opportunity-based advanced fields to `semantic_gold.player_season`:

- `assist_percentage`
- `offensive_rebound_percentage`
- `defensive_rebound_percentage`
- `rebound_percentage`

## What changed

- extended `PlayerSeason` to read `silver.player_game_opportunity_context`
- rolled up season totals for:
  - `teammate_field_goals_made_while_on_court`
  - offensive rebound opportunities
  - defensive rebound opportunities
  - total rebound opportunities
- computed the 4 season percentages from those higher-quality silver denominators

## Updated files

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`

## Follow-up

- `usage_percentage` is still the remaining player-season advanced field from this family
- if added later, it should roll up from `silver.player_game_possession_context.used_offensive_possessions`
