# Batch 29

## Change

Rename rebound fields on the shared semantic game box-score surfaces.

- `rebounds_defensive` -> `defensive_rebounds`
- `rebounds_offensive` -> `offensive_rebounds`
- `rebounds_total` -> `total_rebounds`

Applied to:
- `PlayerGame`
- `TeamGame`

## Why

- the new names match natural basketball language more closely
- they are easier for prompt-to-query generation to interpret
- they keep the public semantic surface more human-readable
