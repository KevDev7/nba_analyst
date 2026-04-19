# Semantic Gold Refactor Batch 4

This batch captures the next ownership cleanup for player identity in the season
aggregate objects.

## Accepted Object Decisions

### 1. Trim duplicated player labels from PlayerSeason and PlayerSeasonTeam

Decision:
- keep `PlayerSeason` and `PlayerSeasonTeam` as real aggregate objects
- remove duplicated `player_name` from both objects

Why:
- `player_name` is an attribute of the `Player` object
- both season aggregate tables already carry `person_id`
- keeping the duplicate label is convenient, but it blurs object ownership in
  the same way `team_name` and `team_abbreviation` did in earlier batches

Remove from `PlayerSeason`:
- `player_name`

Remove from `PlayerSeasonTeam`:
- `player_name`

Keep on both objects:
- `person_id`
- all season grain fields
- all season aggregate measures

Links:
- `PlayerSeason -> Player` via `person_id`
- `PlayerSeasonTeam -> Player` via `person_id`

Important note:
- this batch is an ownership cleanup, not a new object split
- `person_id` already exists on both objects, so no new key is required

Deferred downstream follow-up:
- trim `PLAYER_SEASON_SCHEMA`
- trim `PLAYER_SEASON_TEAM_SCHEMA`
- update the `player_season` transform
- update the `player_season_team` transform
- update attribute inventory
- update semantic gold tests
- redeploy `player_season` and `player_season_team` in Athena/Glue
