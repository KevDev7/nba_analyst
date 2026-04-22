# Batch 27

## Change

Convert `PlayerGame.is_starter` and `PlayerGame.did_play` from `0/1` integers to booleans.

## Why

- both fields are true semantic flags
- `boolean` is clearer than warehouse-style `bigint`
- this makes the public `PlayerGame` surface easier for the model and users to interpret

## Scope

- update the `PlayerGame` semantic contract
- emit booleans from the transform
- refresh tests and generated semantic artifacts
- rebuild and redeploy the live `semantic_gold.player_game` table
