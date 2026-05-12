# Batch 53

Date: 2026-04-20

Scope:
- add raw season possession totals to `semantic_gold.team_season`

Changes:
- added:
  - `offensive_possessions`
  - `defensive_possessions`
- values come from season sums of `silver.team_game_possession_context`
- kept existing:
  - `possessions`
  - as the hybrid averaged season possession count used by ratings and pace

Notes:
- exposed the raw offensive and defensive season totals directly
- kept types as floating point because the silver source and legacy gold totals are doubles
