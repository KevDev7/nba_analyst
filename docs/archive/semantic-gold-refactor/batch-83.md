# Batch 83

Added 7 season total columns to `semantic_gold.team_season`:

- `offensive_rebounds_total`
- `defensive_rebounds_total`
- `field_goals_made_total`
- `field_goals_attempted_total`
- `three_pointers_made_total`
- `three_pointers_attempted_total`
- `free_throws_attempted_total`

Implementation notes:

- This is mostly an exposure pass.
- All 7 totals were already being accumulated inside the existing `team_season` rollup.
- `free_throws_made_total` was intentionally left out of this batch because it is not yet rolled up internally.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
