# Batch 45

## Goal
Expand `TeamGame` with clean opponent box-score mirror measures sourced from the
opposing `silver.boxscore_team_game` row.

## Changes
- added opponent shooting totals and percentages:
  - `opponent_field_goals_attempted`
  - `opponent_field_goals_made`
  - `opponent_field_goals_percentage`
  - `opponent_three_pointers_attempted`
  - `opponent_three_pointers_made`
  - `opponent_three_pointers_percentage`
  - `opponent_free_throws_attempted`
  - `opponent_free_throws_made`
  - `opponent_free_throws_percentage`
- added opponent rebound measures:
  - `opponent_offensive_rebounds`
  - `opponent_defensive_rebounds`
  - `opponent_total_rebounds`
- added opponent playmaking / turnover / foul mirrors:
  - `opponent_assists`
  - `opponent_turnovers`
  - `opponent_steals`
  - `opponent_personal_fouls_committed`
  - `opponent_fouls_drawn`

## Why
- these are clean opponent-row mirrors at the same team-in-game grain
- they make `TeamGame` more expressive for opponent-context prompts without
  needing extra joins
- we explicitly skipped duplicates already represented by better existing names
  like `opponent_score` and `point_differential`

## Verification
- semantic_gold tests cover the new opponent mirror fields
- live Athena/Glue `semantic_gold.team_game` should expose all 17 additions
