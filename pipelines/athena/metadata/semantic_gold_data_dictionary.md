# Semantic Gold Data Dictionary

This document defines the `semantic_gold` v1 surface for `nba_analyst`.

The explicit column classification inventory lives at:
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`

The explicit live ontology graph artifact lives at:
- `docs/supported-ontology-graph.md`

Design rules:
- silver-first inputs only
- current-state business objects
- clean object names
- explicit business grain
- no warehouse surrogate keys on public semantic tables
- no lineage or build timestamps on public semantic tables

## V1 Tables

| Table | Grain | Purpose |
| --- | --- | --- |
| `player` | One row per `person_id` | Current-state player object combining core identity and accepted enrichment fields. |
| `team` | One row per `team_id` | Current-state NBA team object. |
| `game` | One row per `game_id` | Canonical game object with schedule and matchup context. |
| `player_game` | One row per `(game_id, person_id)` | Player participation object with boxscore measures and game/team context. |
| `team_game` | One row per `(game_id, team_id)` | Team participation object with team-game boxscore measures and opponent context. |

## Object Links

- `player_game.person_id -> player.person_id`
- `player_game.game_id -> game.game_id`
- `player_game.team_id -> team.team_id`
- `team_game.game_id -> game.game_id`
- `team_game.team_id -> team.team_id`
- `team_game.opponent_team_id -> team.team_id`

## Column Role Rules

### Primary keys
- `player.person_id`
- `team.team_id`
- `game.game_id`
- `player_game.(game_id, person_id)`
- `team_game.(game_id, team_id)`

### Dimensions
- identity, naming, season, date, opponent, participation-state, and classification fields

### Measures
- quantitative boxscore fields such as `points`, `assists`, `rebounds_total`, `score`, and `minutes_played_decimal`

### Internal fields excluded from V1
- warehouse surrogate keys like `player_sk`, `team_sk`, `game_sk`, `date_sk`
- lineage fields like `record_source`
- build timestamps like `created_at_utc` and `updated_at_utc`
- audit-only raw fields and source metadata columns

## Intentional V1 Exclusions

V1 does not include:
- `player_season`
- `team_season`
- awards
- percentile sidecars
- provenance sidecars
- advanced metric views
- a semantic `date` object
