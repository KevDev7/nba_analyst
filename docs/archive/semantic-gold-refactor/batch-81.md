# Batch 81

Added `block_percentage` to `semantic_gold.team_game`.

Implementation notes:

- This uses the existing team-game defensive shot sidecar:
  `silver/team_game_defensive_shot_context.parquet`
- Formula:
  `100 * blocks / opponent_two_point_attempts`
- No new silver table work was needed.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
