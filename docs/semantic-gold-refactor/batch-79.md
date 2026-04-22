# Batch 79

Removed these contextual fields from `semantic_gold.player_game`:

- `points_off_turnovers`
- `opponent_points_off_turnovers`
- `opponent_second_chance_points`
- `opponent_fast_break_points`
- `opponent_points_in_paint`

Notes:

- These fields were not being populated by the current `player_game` transform.
- They also did not fit the tighter rule that `player_game` should stay focused on the player's own game performance and on-court analytics.
