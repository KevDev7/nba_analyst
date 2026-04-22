# Batch 80

Added these team-game advanced measures to `semantic_gold.team_game`:

- `assist_percentage`
- `three_point_attempt_rate`
- `free_throw_attempt_rate`
- `offensive_rebound_percentage`
- `defensive_rebound_percentage`
- `rebound_percentage`
- `steal_percentage`

Implementation notes:

- These all use the team-game versions of the formulas, not player-game semantics.
- The batch uses only existing `team_game` box score inputs plus `silver/team_game_possession_context.parquet`.
- `block_percentage` was intentionally left out for now.

Updated:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_game_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py`
- `pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py`
- regenerated ontology artifacts

Verification:

- `python3 -m pytest pipelines/athena/tests/semantic_gold/test_semantic_gold_schema.py pipelines/athena/tests/semantic_gold/test_semantic_gold_transforms.py pipelines/athena/tests/semantic_gold/test_deploy_semantic_gold_tables.py -q`
