# Batch 88

Added 12 per-game fields to `semantic_gold.player_season`:

- `steals_per_game`
- `blocks_per_game`
- `field_goals_made_per_game`
- `field_goals_attempted_per_game`
- `three_pointers_made_per_game`
- `three_pointers_attempted_per_game`
- `free_throws_made_per_game`
- `free_throws_attempted_per_game`
- `offensive_rebounds_per_game`
- `defensive_rebounds_per_game`
- `turnovers_per_game`
- `personal_fouls_committed_per_game`

Implementation notes:

- This was an exposure pass from existing season totals plus `games_played`.
- Each field uses the existing `_rounded_ratio(total, games_played)` pattern.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
