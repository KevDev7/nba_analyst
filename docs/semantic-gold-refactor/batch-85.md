# Batch 85

Added 6 team counting totals to `semantic_gold.team_season`:

- `points_total`
- `assists_total`
- `turnovers_total`
- `steals_total`
- `blocks_total`
- `rebounds_total`

Implementation notes:

- This was an exposure pass.
- All 6 values were already being aggregated inside the existing `team_season` rollup.
- `points_total` is exposed from the existing internal `score_total` aggregate.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
