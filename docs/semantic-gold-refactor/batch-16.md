# Semantic Gold Refactor Batch 16

This batch removes source schedule identifier metadata from the public `Game`
object.

## Accepted Object Decisions

### 1. Remove `game_code` from Game

Decision:
- remove `game_code` from the public `Game` surface

Why:
- `game_id` is already the stable public identifier for a game
- `game_code` is mostly source/schedule metadata rather than a strong
  user-facing semantic concept
- analytics questions are not meaningfully improved by exposing the schedule
  code string in the public contract

Remove from `Game`:
- `game_code`

Keep on `Game`:
- `game_id`
- `game_date`
- `game_datetime_utc`
- remaining durable venue, attendance, and matchup context

Result:
- the public `Game` object is less tied to source schedule encoding

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
