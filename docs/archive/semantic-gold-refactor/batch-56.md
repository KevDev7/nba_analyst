# Batch 56

Date: 2026-04-20

Scope:
- rename season scoring rate fields on the player season surfaces

Changes:
- renamed on `semantic_gold.player_season`:
  - `average_points` -> `points_per_game`
- renamed on `semantic_gold.player_season_team`:
  - `average_points` -> `points_per_game`

Notes:
- kept the existing calculation logic
- updated semantic ontology generation inputs so the public metric name matches the renamed attributes
