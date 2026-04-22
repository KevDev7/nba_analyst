# Batch 93

Expanded `player_season_team` with the shooting totals, per-game fields, and shooting percentages for the player-team-season stint grain.

Added:

- `field_goals_made_total`
- `field_goals_made_per_game`
- `field_goals_attempted_total`
- `field_goals_attempted_per_game`
- `field_goals_percentage`
- `two_pointers_made_total`
- `two_pointers_made_per_game`
- `two_pointers_attempted_total`
- `two_pointers_attempted_per_game`
- `two_pointers_percentage`
- `three_pointers_made_total`
- `three_pointers_made_per_game`
- `three_pointers_attempted_total`
- `three_pointers_attempted_per_game`
- `three_pointers_percentage`
- `free_throws_made_total`
- `free_throws_made_per_game`
- `free_throws_attempted_total`
- `free_throws_attempted_per_game`
- `free_throws_percentage`

Notes:

- These are computed from the player's `player_game` rows for that specific team stint only.
- Shooting percentages are recomputed from aggregated stint totals, not averaged from game-level percentages.
