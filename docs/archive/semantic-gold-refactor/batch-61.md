# Batch 61

Added the higher-quality possession / on-court context advanced block to `semantic_gold.player_season`.

Added:
- `offensive_rating`
- `defensive_rating`
- `net_rating`
- `possessions`
- `pace`
- `steal_percentage`
- `block_percentage`

Notes:
- these fields are sourced from the counted silver context path, not the older proxy formulas
- `offensive_rating`, `defensive_rating`, `net_rating`, `possessions`, and `pace` use season aggregates from:
  - `silver/player_game_possession_context.parquet`
- `block_percentage` uses season aggregates from:
  - `silver/player_game_defensive_shot_context.parquet`
- this keeps `PlayerSeason` aligned with the higher-quality player season advanced lineage already used in old gold
