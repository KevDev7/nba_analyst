# Batch 34

## Decision

Change `PlayerSeason.is_multi_team_season` from `bigint` to `boolean`.

## Why

- the field is a true flag, not a count
- `true` / `false` is clearer than `1` / `0`
- this makes the semantic surface less warehouse-shaped

## Scope

Update:

- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/semantic_gold/transform_to_player_season_parquet.py`
- semantic gold tests
- live `semantic_gold.player_season`
