# Batch 38

## Decision

Remove `team_slug` from the public `Team` surface.

## Why

- `team_slug` is more like web/source metadata than core team semantics
- user matching for strings like `warriors` can live in alias/entity-resolution logic instead
- `Team` stays cleaner when it focuses on business-facing identifiers and geography

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- generated semantic artifacts
- live `semantic_gold.team`
