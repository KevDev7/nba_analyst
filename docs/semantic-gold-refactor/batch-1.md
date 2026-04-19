# Semantic Gold Refactor Batch 1

This batch captures the first round of object-model changes while we reshape
`semantic_gold`.

## Accepted Object Decisions

### 1. Arena split from Game

Decision:
- create a new `Arena` object/table

Why:
- these columns describe a stable real-world entity rather than game-specific state
- the arena attributes are reusable across many games
- this is a clean ontology split, not just cosmetic denormalization

Move from `Game` to `Arena`:
- `arena_name`
- `arena_city`
- `arena_state`
- `arena_country`
- `arena_timezone`

Keep on `Game`:
- `arena_id`

New link:
- `Game -> Arena` via `arena_id`

Expected `Arena` shape:
- primary key:
  - `arena_id`
- dimensions:
  - `arena_name`
  - `arena_city`
  - `arena_state`
  - `arena_country`
  - `arena_timezone`

Deferred downstream follow-up:
- add `ARENA_SCHEMA`
- add `semantic_gold/arena/arena.parquet`
- trim `GAME_SCHEMA`
- update inventory and ontology generation
- regenerate capabilities
- update tests and deployment
