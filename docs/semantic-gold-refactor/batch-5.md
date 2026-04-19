# Semantic Gold Refactor Batch 5

This batch captures the next ownership cleanup for home/away team identity in
the `Game` object.

## Accepted Object Decisions

### 1. Trim duplicated home/away team descriptors from Game

Decision:
- keep `Game` as the game object
- keep `home_team_id` and `away_team_id` on `Game`
- remove duplicated home/away team descriptor columns from `Game`

Why:
- the duplicated home/away descriptors are attributes of the `Team` object
- `Game` already has the correct links through `home_team_id` and `away_team_id`
- keeping the ids preserves game structure while cleaning object ownership

Remove from `Game`:
- `home_team_name`
- `away_team_name`
- `home_team_city`
- `away_team_city`
- `home_team_abbreviation`
- `away_team_abbreviation`
- `home_team_slug`
- `away_team_slug`

Keep on `Game`:
- `home_team_id`
- `away_team_id`
- all real game context and measures

Links:
- `Game -> Team` via `home_team_id`
- `Game -> Team` via `away_team_id`

Important note:
- this batch is another ownership cleanup, not a new object split
- home/away role still belongs on the `Game` relationship itself; only the
  duplicated `Team` descriptors are being trimmed

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update the `game` transform
- update attribute inventory
- update semantic gold tests
- redeploy `game` in Athena/Glue
