# Batch 50

Date: 2026-04-20

## Summary

Expanded `semantic_gold.team_season` with the next possession-based and defensive-context season metrics.

## Added Fields

- `minutes`
- `possessions`
- `pace`
- `offensive_rating`
- `defensive_rating`
- `net_rating`
- `steal_percentage`
- `block_percentage`
- `turnover_ratio`

## Why

These metrics are part of the high-value advanced team season surface already proven in the old gold advanced view. They needed richer season context than the first wave because they depend on possession totals or opponent two-point-attempt context.

## Implementation Notes

- `minutes` is derived from aggregated `TeamGame.minutes_played`
- `possessions`, `pace`, `offensive_rating`, `defensive_rating`, `net_rating`, `steal_percentage`, and `turnover_ratio` use season totals from `silver.team_game_possession_context`
- `block_percentage` uses season totals from `silver.team_game_defensive_shot_context`
- formulas follow the existing old-gold advanced season logic rather than inventing a new stat definition
