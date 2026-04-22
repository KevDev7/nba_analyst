# Semantic Gold Refactor Batch 18

This batch removes `attendance` from the public `Game` object.

## Accepted Object Decisions

### 1. Remove attendance from Game

Decision:
- remove `attendance` from the public `Game` surface

Why:
- `attendance` is real postgame data, but it is not central to the main
  analytics questions this product is optimizing for
- keeping it on `Game` widens the public contract with a low-frequency field
  that is better treated as optional enrichment than core game semantics

Remove from `Game`:
- `attendance`

Keep on `Game`:
- `game_id`
- `season_year`
- `season_type`
- `game_date`
- `game_datetime_utc`
- `is_neutral_site`
- `duration_minutes`
- `arena_id`
- `home_team_id`
- `away_team_id`

Result:
- the public `Game` object is narrowed further toward the smallest set of
  durable semantics likely to matter for user questions

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
