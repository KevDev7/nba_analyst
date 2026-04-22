# Batch 86

Added 6 shooting fields to `semantic_gold.team_season`:

- `field_goals_percentage`
- `two_pointers_attempted_total`
- `two_pointers_made_total`
- `two_pointers_percentage`
- `three_pointers_percentage`
- `free_throws_percentage`

Implementation notes:

- `field_goals_percentage`, `three_pointers_percentage`, and `free_throws_percentage` are derived from existing season totals.
- `two_pointers_made_total` and `two_pointers_attempted_total` required a small new season rollup from `team_game`.
- `two_pointers_percentage` is computed from those new two-point totals.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_season_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
