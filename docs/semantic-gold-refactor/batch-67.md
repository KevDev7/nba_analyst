# Batch 67

Added a second wave of advanced `PlayerGame` metrics to `semantic_gold.player_game`:

- `three_point_attempt_rate`
- `free_throw_attempt_rate`
- `offensive_rating`
- `defensive_rating`
- `net_rating`
- `steal_percentage`
- `block_percentage`

Implementation notes:

- `three_point_attempt_rate` and `free_throw_attempt_rate` are derived directly from player-game box score totals.
- `offensive_rating`, `defensive_rating`, and `net_rating` use the player on-court possession context from `silver.player_game_possession_context`.
- `steal_percentage` uses defensive possessions while on court.
- `block_percentage` uses opponent two-point attempts while on court from `silver.player_game_defensive_shot_context`.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
