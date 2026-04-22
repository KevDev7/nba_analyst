# Batch 84

Added `free_throws_made_total` to `semantic_gold.team_season`.

Implementation notes:

- This completes the free-throw total pair on `team_season`.
- Unlike the previous 7-column pass, this one needed a small real rollup change:
  - initialize `free_throws_made_total`
  - aggregate it from `team_game.free_throws_made`
  - expose it in the final `team_season` row

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
