# Batch 72

Removed `possessions_total` from `semantic_gold.player_game` and replaced it with the cleaner public `possessions` field.

## Why

At player-game grain, `possessions_total` was a raw summed context field:

- `offensive_possessions + defensive_possessions`

That is not the usual basketball-facing possession stat. The cleaner semantic stat is:

- `possessions = (offensive_possessions + defensive_possessions) / 2`

This matches how `semantic_gold.player_season` already treats public `possessions`.

## Changes

- removed `possessions_total` from the `player_game` schema
- added `possessions` to the `player_game` schema
- compute `possessions` as the averaged/blended game possession value
- updated inventory, tests, and downstream semantic artifacts

## Notes

- `offensive_possessions` and `defensive_possessions` remain on `player_game`
- this is a semantic cleanup, not a source-methodology change
