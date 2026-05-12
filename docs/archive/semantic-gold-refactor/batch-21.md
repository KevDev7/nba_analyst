# Semantic Gold Refactor Batch 21

This batch removes redundant full-name presentation duplication from the public
`Player` object.

## Accepted Object Decisions

### 1. Remove `display_name` from Player

Decision:
- remove `display_name` from the public `Player` surface

Why:
- live data shows `display_name` is not currently distinct from `player_name`
- keeping both fields duplicates the same full-name concept in two public
  columns
- the player surface is cleaner when one canonical full-name field is exposed

Remove from `Player`:
- `display_name`

Keep on `Player`:
- `player_name`
- `first_name`
- `family_name`
- the rest of the canonical player profile fields

Result:
- the public `Player` object uses one canonical full-name field instead of two
  overlapping full-name fields

Deferred downstream follow-up:
- trim `PLAYER_SCHEMA`
- update the player transform
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `player` in Athena/Glue
