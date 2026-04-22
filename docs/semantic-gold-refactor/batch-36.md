# Batch 36

## Decision

Add two truthful geography fields to `Team`:

- `team_state`
- `team_country`

## Why

- `team_city` alone does not fully capture franchise geography
- state/province and country are stable team-level attributes
- these fields make the `Team` object more informative without overcomplicating the schema

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_team_parquet.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- semantic gold tests
- generated semantic artifacts
- live `semantic_gold.team`
