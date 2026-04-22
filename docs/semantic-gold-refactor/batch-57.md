# Batch 57

Expanded `semantic_gold.player_season` from a minimal points summary into a richer season box-score snapshot.

Added:
- `age_on_jan_31`
- `games_started`
- `minutes_per_game`
- `assists_total`
- `assists_per_game`
- `rebounds_total`
- `rebounds_per_game`
- `field_goals_percentage`
- `three_pointers_percentage`
- `free_throws_percentage`
- `double_doubles`
- `triple_doubles`

Notes:
- `age_on_jan_31` uses the same January 31 season-age convention as legacy gold and pulls from the player bio birth-date path with BBR fallback.
- double-double and triple-double counts use the standard five box-score categories:
  - points
  - rebounds
  - assists
  - steals
  - blocks
- this batch only expands `PlayerSeason`; `PlayerSeasonTeam` stays unchanged for now.
