# Semantic Gold Refactor Batch 3

This batch captures the next team-identity cleanup in the season aggregate
objects.

## Accepted Object Decisions

### 1. Trim duplicated team labels from PlayerSeasonTeam and TeamSeason

Decision:
- keep `PlayerSeasonTeam` and `TeamSeason` as real aggregate objects
- remove duplicated team label columns from both objects

Why:
- `team_name` and `team_abbreviation` are attributes of the `Team` object
- both season aggregate tables already carry `team_id`
- the duplicate labels are convenient, but they blur object ownership in the
  same way `TeamGame` did before Batch 2

Remove from `PlayerSeasonTeam`:
- `team_name`
- `team_abbreviation`

Remove from `TeamSeason`:
- `team_name`
- `team_abbreviation`

Keep on both objects:
- `team_id`
- all season grain fields
- all season aggregate measures

Links:
- `PlayerSeasonTeam -> Team` via `team_id`
- `TeamSeason -> Team` via `team_id`

Important note:
- this batch is another object-boundary cleanup, not a new object split
- `team_side` is not part of this cleanup because it is a participation/context
  attribute, not a `Team` attribute

Deferred downstream follow-up:
- trim `PLAYER_SEASON_TEAM_SCHEMA`
- trim `TEAM_SEASON_SCHEMA`
- update the `player_season_team` transform
- update the `team_season` transform
- update attribute inventory
- update semantic gold tests
- redeploy `player_season_team` and `team_season` in Athena/Glue
