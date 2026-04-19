# Batch 28

## Change

Rename the committed-foul fields on the shared semantic game box-score surfaces.

- `fouls_offensive` -> `offensive_fouls_committed`
- `fouls_personal` -> `personal_fouls_committed`
- `fouls_technical` -> `technical_fouls_committed`

Applied to:
- `PlayerGame`
- `TeamGame`

## Why

- the old names mixed foul type and direction awkwardly
- the new names make it clearer that these are fouls committed by the player or team
- `fouls_drawn` already reads clearly and stays unchanged
