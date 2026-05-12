# Batch 68

Added season total shooting and rebound columns to `semantic_gold.player_season`:

- `field_goals_made_total`
- `field_goals_attempted_total`
- `free_throws_made_total`
- `free_throws_attempted_total`
- `three_pointers_made_total`
- `three_pointers_attempted_total`
- `offensive_rebounds_total`
- `defensive_rebounds_total`

Implementation notes:

- This batch only exposes totals that were already being accumulated inside the `PlayerSeason` rollup.
- No new silver inputs or new aggregation logic were required.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
