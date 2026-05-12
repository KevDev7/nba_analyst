# Batch 90

Added `team_season` per-game fields derived from existing season totals and `games_played`:

- `minutes_per_game`
- `points_per_game`
- `rebounds_per_game`
- `assists_per_game`
- `steals_per_game`
- `blocks_per_game`
- `field_goals_made_per_game`
- `field_goals_attempted_per_game`
- `two_pointers_made_per_game`
- `two_pointers_attempted_per_game`
- `three_pointers_made_per_game`
- `three_pointers_attempted_per_game`
- `free_throws_made_per_game`
- `free_throws_attempted_per_game`
- `offensive_rebounds_per_game`
- `defensive_rebounds_per_game`
- `turnovers_per_game`
- `personal_fouls_committed_per_game`

Notes:

- This was an exposure pass only. All required season totals already existed in the `team_season` rollup.
- `minutes_per_game` is derived from team minutes (`minutes_played_total / 5`) before dividing by `games_played`.
