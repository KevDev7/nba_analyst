# Semantic Gold Refactor Batch 13

This batch removes sparse schedule-label and special-event metadata from the
public `Game` object.

## Accepted Object Decisions

### 1. Remove low-value schedule labeling fields from Game

Decision:
- remove `is_if_necessary`, `game_label`, `game_sublabel`, `game_subtype`,
  `series_game_number`, and `series_text` from the public `Game` surface

Why:
- live values show these fields are mostly sparse schedule labeling rather than
  durable analytics semantics
- `is_if_necessary` is effectively unused in the current live data
- `series_game_number` and `series_text` are effectively unused in the current
  live data
- `game_label`, `game_sublabel`, and `game_subtype` mostly describe special
  event branding such as cup, all-star, and global-game labeling
- keeping them on `Game` makes the public object feel more like a schedule
  marketing surface than a clean analytics object

Remove from `Game`:
- `is_if_necessary`
- `game_label`
- `game_sublabel`
- `game_subtype`
- `series_game_number`
- `series_text`

Keep on `Game`:
- game identity and timing fields
- venue and team links
- durable postgame context like `duration_minutes`, `attendance`, `is_sellout`,
  and `is_neutral_site`

Result:
- the public `Game` object is narrower and more clearly centered on durable
  postgame analytics context

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
