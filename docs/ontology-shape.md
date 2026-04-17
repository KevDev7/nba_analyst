# Ontology Shape

This doc defines the live ontology after the gold-first slice-4 cutover.

## Live Objects

### `Player`

Backing table:

- `player`

Attributes:

- primary key:
  - `person_id`
- dimensions:
  - `player_name`
  - `display_name`
  - `primary_position`

### `PlayerGame`

Backing table:

- `player_game`

Attributes:

- primary key:
  - `player_game_id`
- dimensions:
  - `person_id`
  - `team`
  - `game_date`
  - `season_year`
  - `season_type`
- measures:
  - `points`
  - `minutes_played_decimal`

## Live Link

- `PlayerGame -> Player`
  - relation type: `many_to_one`
  - join path:
    - `player_game.person_id -> player.person_id`

## Live Metrics

Executable now:

- `total_points`
  - formula: `SUM(points)`
- `average_points`
  - formula: `AVG(points)`

Scaffolded but not executable yet:

- `games_played`
- `points_per_36`

## Why This Matters

The ontology is no longer just typed metadata over synthetic tables.

It is now the live semantic contract for:

- real gold-derived local data
- real object/link validation
- governed metric resolution in grounded planning
