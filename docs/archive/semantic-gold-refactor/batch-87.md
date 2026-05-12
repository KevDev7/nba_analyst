# Batch 87

Added 4 foul totals to `semantic_gold.team_season`:

- `offensive_fouls_committed_total`
- `fouls_drawn_total`
- `personal_fouls_committed_total`
- `technical_fouls_committed_total`

Implementation notes:

- This is a straightforward season rollup from existing `team_game` fields.
- No new silver work was needed.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
