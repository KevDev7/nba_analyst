# Grounded Planning

This doc pins down the live grounded-planning behavior after slice 4.

## Inputs

Grounded planning accepts:

- `MetricQuery`
- `ObjectQuery`

## Validation

Validation now checks the ontology contract directly:

- required objects exist
- required attributes exist with the right kinds
- required link exists
- requested metric exists in the ontology
- metric is executable in this slice
- filter placement is valid on the fact side
- ordering matches the selected metric

## Resolution

Resolution now produces:

- final fact table
- row/display table
- join path
- governed metric formula
- filter location
- required columns for execution

Example for `average_points`:

- fact table: `player_game`
- row table: `player`
- join path:
  - `player_game.person_id -> player.person_id`
- filter:
  - `LastNGames` on recent `PlayerGame` rows
- formula:
  - `AVG(points)`

## Output Plans

The runtime plan contract now distinguishes:

- ranking over `total_points`
- ranking over `average_points`
- object rows with attached `total_points`
- comparison over `total_points`

The important change is that grounded planning now resolves governed metric formulas, not just table paths.
