# Batch 63

Added `usage_percentage` to `semantic_gold.player_game`.

## What changed

- extended `PlayerGame` to read `used_offensive_possessions` from `silver.player_game_possession_context`
- computed `usage_percentage` as:
  - `100 * used_offensive_possessions / offensive_possessions`
- returned `NULL` when `offensive_possessions` is missing or zero

## Updated files

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`

## Follow-up

- if we later add `usage_percentage` to `PlayerSeason`, it should roll up from the same higher-quality silver possession-context path rather than the old proxy-only formula
