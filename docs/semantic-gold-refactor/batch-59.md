# Batch 59

Added `minutes_total` to `semantic_gold.player_season`.

Reason:
- pair `minutes_total` with the already-exposed `minutes_per_game`
- expose season playing-time volume directly instead of forcing everything through per-game rates

Notes:
- `minutes_total` is stored as decimal minutes (`double`)
- it is sourced directly from the existing `PlayerSeason` rollup of `PlayerGame.minutes_played`
