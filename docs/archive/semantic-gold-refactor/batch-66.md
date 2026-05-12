# Batch 66

Added the first game-grain advanced shooting and achievement flags to `semantic_gold.player_game`:

- `assist_to_turnover_ratio`
- `effective_field_goal_percentage`
- `true_shooting_percentage`
- `is_double_double`
- `is_triple_double`

## What changed

- computed player-game assist-to-turnover ratio directly from game box score totals
- computed player-game `effective_field_goal_percentage`
- computed player-game `true_shooting_percentage`
- added game-level double-double / triple-double flags using the standard five-category rule:
  - points
  - rebounds
  - assists
  - steals
  - blocks

## Updated files

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`

## Follow-up

- if we later want a fuller player-game advanced batch, the next likely candidates are:
  - `assist_ratio`
  - `turnover_ratio`
  - `three_point_attempt_rate`
  - `free_throw_attempt_rate`
