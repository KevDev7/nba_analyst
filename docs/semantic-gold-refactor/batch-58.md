# Batch 58

Renamed the player season total-points field for consistency:

- `total_points` -> `points_total`

Applied to:
- `semantic_gold.player_season`
- `semantic_gold.player_season_team`

Reason:
- keep season total-stat names on a consistent `stat_total` pattern
- align with fields like `assists_total` and `rebounds_total`
