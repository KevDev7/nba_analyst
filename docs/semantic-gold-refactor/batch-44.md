# Batch 44

## Goal
Expand `TeamGame` with NBA-style point-context totals that are already supported
cleanly by `silver.boxscore_team_game`.

## Changes
- added `points_off_turnovers`
- added `opponent_points_off_turnovers`
- added `opponent_second_chance_points`
- added `opponent_fast_break_points`
- added `opponent_points_in_paint`
- aligned the internal `TeamGame` dedupe quality score with the current field
  names

## Why
- these are game-grain team context stats the NBA itself surfaces directly
- the opponent versions fit naturally on `TeamGame` because the table already
  carries opponent-relative context like `opponent_team_id` and `opponent_score`
- this avoids relying on murkier attempted/made source stat families

## Verification
- semantic_gold tests cover the new `TeamGame` columns
- live Athena/Glue `semantic_gold.team_game` should expose all five additions
