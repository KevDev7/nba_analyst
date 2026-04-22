# Semantic Gold Refactor Batch 11

This batch removes low-value live-state and operational status fields from the
public `Game` object.

## Accepted Object Decisions

### 1. Remove live-game state and operational status helpers from Game

Decision:
- remove `current_period`, `game_clock`, `game_status_code`, and
  `game_status_text` from the public `Game` surface

Why:
- `current_period` and `game_clock` are feed-state fields that are mainly useful
  while a game is in progress
- `game_status_code` and `game_status_text` are operational metadata rather
  than core postgame analytics semantics
- keeping them on the public object expands the semantic surface with fields
  that are more scoreboard-state than business-facing game identity

Remove from `Game`:
- `current_period`
- `game_clock`
- `game_status_code`
- `game_status_text`

Keep on `Game`:
- game identity fields
- schedule and series context
- venue and team links
- durable postgame context like `duration_minutes`, `attendance`,
  `is_sellout`, and `regulation_periods`

Result:
- the public `Game` object is more clearly shaped around durable game context
  rather than live scoreboard state

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
