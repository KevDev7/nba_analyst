# Grounded Planning

This doc pins down the current live grounded-planning behavior.

For the explicit supported ontology graph that current path resolution is
expected to use, see:

- [supported-ontology-graph.md](/Users/HungNguyen/Desktop/Projects/nba_analyst/docs/supported-ontology-graph.md)

## Inputs

Grounded planning accepts:

- `MetricQuery`
- `ObjectQuery`
- `FindQuery`

## Validation

Validation now checks the ontology contract directly:

- required objects exist
- required attributes exist with the right kinds
- a valid ontology path exists from the fact object to the requested row object
- a valid context path exists when the selected output needs linked context
- requested metric exists in the ontology
- metric is executable in this slice
- time scopes are valid for the selected fact surface
- row predicate placement is valid before grouping
- result predicate placement is valid after grouping
- ordering/limit requests are valid for the result shape

## Resolution

Resolution now produces:

- final fact table
- row/display table
- discovered row path
- optional discovered context path
- governed metric formula
- grouped dimensions and display metadata
- grounded row/result/find predicate trees
- time scope and optional time grain
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

- ranking/top-N
- grouped aggregate
- object rows
- find rows
- time-series trend
- comparison, including grouped comparison breakdowns

The important change is that grounded planning resolves governed metric
formulas, graph-derived paths, grouping columns, display metadata, predicates,
and time scopes before Python executes anything.
