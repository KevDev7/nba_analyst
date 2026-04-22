# Batch 78

Removed `did_play` from `semantic_gold.player_game`.

Notes:

- `player_game` already only includes rows for players who played, so `did_play` was redundant on the public surface.
- The internal transform still uses the source `played` flag to filter rows, but the public object no longer exposes it.
