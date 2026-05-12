# Batch 92

Expanded `player_season_team` with the first stint-level season bucket from `player_season`.

Added:

- `games_started`
- `minutes_total`
- `minutes_per_game`
- `assists_total`
- `assists_per_game`
- `rebounds_total`
- `rebounds_per_game`
- `offensive_rebounds_total`
- `offensive_rebounds_per_game`
- `defensive_rebounds_total`
- `defensive_rebounds_per_game`
- `steals_total`
- `steals_per_game`
- `blocks_total`
- `blocks_per_game`
- `opponent_blocks_total`
- `turnovers_total`
- `turnovers_per_game`
- `plus_minus_total`
- `offensive_fouls_committed_total`
- `personal_fouls_committed_total`
- `personal_fouls_committed_per_game`
- `technical_fouls_committed_total`
- `fouls_drawn_total`
- `fast_break_points_total`
- `points_in_paint_total`
- `second_chance_points_total`

Notes:

- These fields are rolled up at the `(person_id, team_id, season_year, season_type)` grain.
- This batch only adds direct boxscore-style totals and per-game fields. It does not yet add shooting or advanced percentage families.
