# Batch 52

Date: 2026-04-20

Scope:
- add possession context to `semantic_gold.player_game`

Changes:
- added:
  - `offensive_possessions`
  - `defensive_possessions`
  - `possessions_total`
- sourced from `silver.player_game_possession_context`
- joined by `(game_id, person_id)`

Notes:
- kept the existing `did_play = true` participation filter
- did not expose possession provenance fields in this batch
- left unrelated existing `PlayerGame` transform drift untouched
