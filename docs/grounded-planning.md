# Grounded Planning

This doc pins down the live grounded-planning behavior after slice 7.

For the explicit supported ontology graph that current path resolution is
expected to use, see:

- [supported-ontology-graph.md](/Users/HungNguyen/Desktop/Projects/nba_analyst/docs/supported-ontology-graph.md)

## Inputs

Grounded planning accepts:

- `MetricQuery`
- `ObjectQuery`

## Validation

Validation now checks the ontology contract directly:

- required objects exist
- required attributes exist with the right kinds
- a valid ontology path exists from the fact object to the requested row object
- a valid context path exists when the selected output needs linked context
- requested metric exists in the ontology
- metric is executable in this slice
- filter placement is valid on the fact side
- ordering matches the selected metric

## Resolution

Resolution now produces:

- final fact table
- row/display table
- discovered row path
- optional discovered context path
- governed metric formula
- filter location
- required columns for execution

Example for `average_points`:

- fact table: `player_game`
- row table: `player`
- discovered row path:
  - `PlayerGame -> Player`
- discovered context path:
  - `PlayerGame -> Team`
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

The important change is that grounded planning now resolves governed metric formulas and graph-derived paths, not just a small set of hand-picked joins.
