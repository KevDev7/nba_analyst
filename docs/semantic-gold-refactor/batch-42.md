# Batch 42

## Goal
Rename the win/loss outcome dimension from `game_result` to
`win_loss_result` so the column meaning is more explicit.

## Changes
- renamed `game_result` -> `win_loss_result` on `PlayerGame`
- renamed `game_result` -> `win_loss_result` on `TeamGame`
- updated `TeamSeason` to aggregate wins and losses from `win_loss_result`
- regenerated semantic ontology and interpreter capabilities

## Why
- `game_result` was slightly vague and could be read as a general result field
- `win_loss_result` makes it explicit that the values are categorical outcome
  labels such as `win` and `loss`

## Verification
- semantic_gold contract and transform tests pass after the rename
- live Athena/Glue should expose `win_loss_result` on `player_game` and
  `team_game`
