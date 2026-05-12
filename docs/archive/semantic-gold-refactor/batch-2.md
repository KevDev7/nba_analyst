# Semantic Gold Refactor Batch 2

This batch captures the `TeamGame` object cleanup work.

## Accepted Object Decisions

### 1. Shave duplicated Team descriptors out of TeamGame

Decision:
- keep `TeamGame` as an object
- do not create any new object from `TeamGame`
- remove duplicated team descriptor columns that already belong to `Team`

Why:
- `TeamGame` already has the real links it needs:
  - `team_id`
  - `opponent_team_id`
- the duplicated descriptor columns blur object ownership
- those descriptors are attributes of `Team`, not true `TeamGame` facts

Remove from `TeamGame`:
- `team_name`
- `team_city`
- `team_abbreviation`
- `opponent_team_name`
- `opponent_team_city`
- `opponent_team_abbreviation`

Keep on `TeamGame`:
- `team_id`
- `opponent_team_id`
- all real game/team context fields
- all team-game measures

Ontology interpretation:
- `TeamGame -> Team` via `team_id`
- `TeamGame -> Team` via `opponent_team_id`

Deferred downstream follow-up:
- trim `TEAM_GAME_SCHEMA`
- update `transform_to_team_game_parquet.py`
- update attribute inventory
- regenerate ontology and capabilities later
- update semantic gold tests
- refresh and redeploy the `team_game` semantic_gold table
