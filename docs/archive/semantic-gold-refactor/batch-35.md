# Batch 35

## Decision

Normalize five `Team.team_city` values to true city names:

- `Golden State` -> `San Francisco`
- `Indiana` -> `Indianapolis`
- `LA` -> `Los Angeles`
- `Minnesota` -> `Minneapolis`
- `New York` -> `New York City`
- `Utah` -> `Salt Lake City`

## Why

- the existing values mix branding and market labels with actual cities
- the semantic `Team` surface should prefer truth over shorter franchise labels
- this keeps `team_city` closer to a real city field without changing the schema

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/transform_to_team_parquet.py`
- semantic gold tests
- live `semantic_gold.team`

## Notes

- this is a data normalization change only
- no schema change is required
