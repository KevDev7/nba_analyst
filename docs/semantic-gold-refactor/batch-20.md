# Semantic Gold Refactor Batch 20

This batch removes redundant boolean position flags from the public `Player`
object.

## Accepted Object Decisions

### 1. Remove `is_guard`, `is_forward`, and `is_center` from Player

Decision:
- remove `is_guard`, `is_forward`, and `is_center` from the public `Player`
  surface

Why:
- `primary_position` and `position_group` already encode the same semantic idea
  in cleaner canonical forms
- the boolean flags are redundant and widen the player contract without adding
  meaningful new semantics
- filtering by position should rely on `primary_position` or `position_group`
  instead of parallel boolean projections

Remove from `Player`:
- `is_guard`
- `is_forward`
- `is_center`

Keep on `Player`:
- `primary_position`
- `position_group`
- the rest of the canonical player identity and profile fields

Result:
- the public `Player` object now uses one canonical position representation
  instead of a duplicated boolean expansion

Deferred downstream follow-up:
- trim `PLAYER_SCHEMA`
- update the player transform
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `player` in Athena/Glue
