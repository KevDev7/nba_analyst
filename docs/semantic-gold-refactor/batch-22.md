# Semantic Gold Refactor Batch 22

This batch renames the public player name fields to a cleaner canonical set.

## Accepted Object Decisions

### 1. Rename player name fields to `full_name`, `first_name`, and `last_name`

Decision:
- rename `player_name` to `full_name`
- keep `first_name`
- rename `family_name` to `last_name`

Why:
- `full_name`, `first_name`, and `last_name` are clearer and more consistent
  than the previous mixed naming
- `player_` prefixes are redundant inside the `Player` object
- `last_name` is more intuitive for product work than `family_name`

Rename on `Player`:
- `player_name` -> `full_name`
- `family_name` -> `last_name`

Keep:
- `first_name`

Result:
- the public `Player` object now uses a simpler and more intuitive name field
  set

Deferred downstream follow-up:
- rename the `PLAYER_SCHEMA` fields
- update the player transform
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `player` in Athena/Glue
