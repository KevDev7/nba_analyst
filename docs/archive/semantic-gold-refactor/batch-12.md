# Semantic Gold Refactor Batch 12

This batch removes low-value schedule and structural helper fields from the
public `Game` object.

## Accepted Object Decisions

### 1. Remove postponed and regulation helpers from Game

Decision:
- remove `postponed_status` and `regulation_periods` from the public `Game`
  surface

Why:
- only completed games are admitted into the semantic layer, so
  `postponed_status` should not matter for rows that exist here
- `regulation_periods` is low-value structural metadata that adds little
  semantic usefulness for user prompts
- both fields widen the public game surface without materially improving
  postgame analytics coverage

Remove from `Game`:
- `postponed_status`
- `regulation_periods`

Keep on `Game`:
- remaining durable schedule and identity context
- venue links and game identity
- core postgame facts like `duration_minutes`, `attendance`, and `is_sellout`

Result:
- the public `Game` object is now oriented around durable postgame identity and
  context rather than operational or structural helper metadata

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
