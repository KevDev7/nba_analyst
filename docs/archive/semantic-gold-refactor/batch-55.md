# Batch 55

Date: 2026-04-20

Scope:
- add advanced possession and efficiency context to `semantic_gold.team_game`

Changes:
- added:
  - `possessions`
  - `offensive_possessions`
  - `defensive_possessions`
  - `offensive_rating`
  - `defensive_rating`
  - `net_rating`
  - `assist_to_turnover_ratio`
  - `effective_field_goal_percentage`
  - `true_shooting_percentage`

Sources:
- possession fields come from `silver.team_game_possession_context`
- efficiency and rating fields are computed from the team-game boxscore row plus possession totals

Notes:
- used `assist_to_turnover_ratio` as the public semantic name instead of the stat-sheet abbreviation
- kept the `TeamGame` possession-context input optional in the shared builder so season transforms remain compatible
