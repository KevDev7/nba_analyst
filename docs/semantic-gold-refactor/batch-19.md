# Semantic Gold Refactor Batch 19

This batch removes low-frequency event-context fields from the public `Game`
object.

## Accepted Object Decisions

### 1. Remove `is_neutral_site` and `duration_minutes` from Game

Decision:
- remove `is_neutral_site` from the public `Game` surface
- remove `duration_minutes` from the public `Game` surface

Why:
- `is_neutral_site` is real context, but low-frequency and not central to the
  main analytics questions this product is optimizing for
- `duration_minutes` is operational/event-length metadata rather than core
  basketball semantics
- both fields widen the public `Game` contract without materially improving the
  most important user-facing analytics workflows

Remove from `Game`:
- `is_neutral_site`
- `duration_minutes`

Keep on `Game`:
- `game_id`
- `season_year`
- `season_type`
- `game_date`
- `game_datetime_utc`
- `arena_id`
- `home_team_id`
- `away_team_id`

Result:
- the public `Game` object is reduced to the minimal durable identity and link
  fields most likely to matter for user questions

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
