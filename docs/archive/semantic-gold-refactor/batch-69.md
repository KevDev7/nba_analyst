# Batch 69

Added `two_pointers_percentage` to `semantic_gold.player_season`.

Implementation notes:

- This required a small season-rollup extension in `PlayerSeason`.
- `two_pointers_made_total` and `two_pointers_attempted_total` are now accumulated internally from `PlayerGame`.
- `two_pointers_percentage` is exposed as the season-level percentage derived from those totals.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
