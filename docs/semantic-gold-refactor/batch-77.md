# Batch 77

Added six more player-level season totals to `semantic_gold.player_season`:

- `blocks_total`
- `fouls_drawn_total`
- `personal_fouls_committed_total`
- `steals_total`
- `turnovers_total`
- `plus_minus_total`

Notes:

- `blocks_total`, `steals_total`, and `turnovers_total` were already being accumulated internally in the season rollup and are now exposed publicly.
- `fouls_drawn_total`, `personal_fouls_committed_total`, and `plus_minus_total` are new season totals summed directly from existing `semantic_gold.player_game` fields.
- `plus_minus_total` follows current semantic naming rather than the older legacy-gold `plus_minus_points_total`.
