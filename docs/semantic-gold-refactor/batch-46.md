# Batch 46

## Goal
Finish the remaining clean opponent-row mirrors on `TeamGame` for two-point
shooting and committed-foul context.

## Changes
- added `opponent_offensive_fouls_committed`
- added `opponent_technical_fouls_committed`
- added `opponent_two_pointers_attempted`
- added `opponent_two_pointers_made`
- added `opponent_two_pointers_percentage`

## Why
- these were the last obvious opponent mirrors missing from stat families that
  already exist on `TeamGame`
- each value maps directly from the opponent row in
  `silver.boxscore_team_game`

## Verification
- semantic_gold tests cover all five new opponent mirror fields
- live Athena/Glue `semantic_gold.team_game` should expose all five additions
