# Semantic Gold Refactor Batch 14

This batch removes redundant alternate timezone renderings of game start time
from the public `Game` object.

## Accepted Object Decisions

### 1. Keep one canonical game timestamp on Game

Decision:
- keep `game_datetime_utc` as the canonical game start timestamp
- remove `local_market_game_datetime_utc`
- remove `home_market_game_datetime_utc`
- remove `away_market_game_datetime_utc`
- remove `eastern_time_game_datetime_utc`

Why:
- all four removed fields are alternate timezone or market renderings of the
  same underlying game start moment
- they create multiple competing public representations for one concept
- `game_datetime_utc` is the clean canonical timestamp for sorting, filtering,
  and time arithmetic
- timezone-specific renderings are better handled in presentation layers than in
  the core semantic object contract

Remove from `Game`:
- `local_market_game_datetime_utc`
- `home_market_game_datetime_utc`
- `away_market_game_datetime_utc`
- `eastern_time_game_datetime_utc`

Keep on `Game`:
- `game_date`
- `game_datetime_utc`
- the rest of the durable game identity/context fields

Result:
- the public `Game` object now exposes one canonical timestamp instead of five
  competing variants

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
