# Batch 32

## Decision

Rename the public `Player` attribute:

- `draft_number` -> `draft_pick_number`

## Why

- `draft_pick_number` is clearer in plain language than `draft_number`
- it better matches how a user is likely to phrase the concept
- it keeps the semantic meaning explicit without changing the underlying silver/gold source field

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- generated semantic artifacts
- live `semantic_gold.player`

## Notes

- this is a public semantic rename only
- lower layers may still keep the underlying source field named `draft_number`
