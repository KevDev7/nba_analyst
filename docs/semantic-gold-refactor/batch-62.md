# Batch 62

## Scope

Add the higher-standard opportunity-based percentages to `semantic_gold.player_game` from the canonical silver player-game opportunity context table.

## Changes

- added `assist_percentage` to `PlayerGame`
- added `offensive_rebound_percentage` to `PlayerGame`
- added `defensive_rebound_percentage` to `PlayerGame`
- added `rebound_percentage` to `PlayerGame`
- sourced the denominators from `silver.player_game_opportunity_context`
- kept the semantic layer responsible only for the public ratio formulas

## Notes

- `assist_percentage` uses `100 * assists / teammate_field_goals_made_while_on_court`
- `offensive_rebound_percentage` uses `100 * offensive_rebounds / offensive_rebound_opportunities_while_on_court`
- `defensive_rebound_percentage` uses `100 * defensive_rebounds / defensive_rebound_opportunities_while_on_court`
- `rebound_percentage` uses `100 * total_rebounds / rebound_opportunities_while_on_court`
- zero or missing denominators stay `NULL`
