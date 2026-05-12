# Batch 70

Added additional player-attributed season totals to `semantic_gold.player_season`:

- `opponent_blocks_total`
- `offensive_fouls_committed_total`
- `technical_fouls_committed_total`
- `fast_break_points_total`
- `points_in_paint_total`
- `second_chance_points_total`

Implementation notes:

- These are summed directly from existing `PlayerGame` fields.
- No new silver inputs were needed.
- This batch intentionally excluded the weaker opponent-context season totals.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
