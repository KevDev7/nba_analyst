# Batch 65

Stabilized `usage_percentage` across the player-grain semantic surfaces by adding a boxscore-proxy fallback when the counted possession numerator is not credible.

## What changed

- kept the counted possession path as the preferred source when it passes basic sanity checks
- added the standard boxscore usage fallback for `PlayerGame`
- added `usage_percentage` to `PlayerSeason`
- added the same fallback logic for `PlayerSeason`, using player season totals plus summed team totals from games the player appeared in
- switched the player transforms to read the richer `team_game` input contract needed for the usage fallback denominators

## Updated files

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_game_parquet.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`

## Follow-up

- the counted `used_offensive_possessions` path in silver still needs a deeper health pass
- once that is fixed, we can reconsider whether the proxy fallback should remain just as a safety net or be narrowed further
