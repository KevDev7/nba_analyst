# Batch 73

Added `pace` to `semantic_gold.player_game`.

## Why

Now that `player_game` has the cleaner public `possessions` field, `pace` is straightforward to expose at the same grain:

- `pace = 48 * possessions / minutes_played`

This keeps the player-game surface aligned with the existing `team_game` and `player_season` advanced stat families.

## Changes

- added `pace` to the `player_game` schema
- compute `pace` from blended `possessions` and `minutes_played`
- updated inventory, tests, and downstream semantic artifacts
