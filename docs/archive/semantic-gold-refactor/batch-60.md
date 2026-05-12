# Batch 60

Added a boxscore-derived advanced stat block to `semantic_gold.player_season`.

Added:
- `assist_to_turnover_ratio`
- `assist_ratio`
- `turnover_ratio`
- `effective_field_goal_percentage`
- `three_point_attempt_rate`
- `free_throw_attempt_rate`
- `true_shooting_percentage`

Notes:
- this batch is intentionally limited to metrics that are cleanly derivable from season boxscore totals
- no new possession or on-court context inputs were needed
- naming uses `assist_to_turnover_ratio` instead of the old abbreviated `ast_to_turnover_ratio`
