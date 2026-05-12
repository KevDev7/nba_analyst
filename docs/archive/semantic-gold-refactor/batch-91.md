# Batch 91

Standardized column ordering across the four core semantic stat surfaces:

- `player_game`
- `player_season`
- `team_game`
- `team_season`

Ordering standard:

- keys and context first
- participation and outcome next
- core counting stats next
- fouls and special scoring buckets next
- shooting families next, with `made` before `attempted`
- possession and impact context next
- advanced rates and efficiency last

Notes:

- This was a schema-ordering pass only. No metric definitions changed.
- The semantic attribute inventory was reordered to match the updated schema contracts.
