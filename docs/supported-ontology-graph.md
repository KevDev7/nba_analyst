# Supported Ontology Graph

This document is the explicit live graph artifact for the current `semantic_gold`
semantic core.

Its purpose is to keep generic path resolution scoped and testable before we
broaden graph search further.

## Canonical Objects

- `Player`
- `Team`
- `Arena`
- `Game`
- `PlayerGame`
- `TeamGame`
- `PlayerSeason`
- `PlayerSeasonTeam`
- `TeamSeason`

## Live Directed Links

These are the ontology links the planner is expected to reason over today.

| Link Name | Source | Target | Relation | Join |
| --- | --- | --- | --- | --- |
| `player_game_player` | `PlayerGame` | `Player` | `many_to_one` | `player_game.person_id -> player.person_id` |
| `player_game_team` | `PlayerGame` | `Team` | `many_to_one` | `player_game.team_id -> team.team_id` |
| `player_game_game` | `PlayerGame` | `Game` | `many_to_one` | `player_game.game_id -> game.game_id` |
| `team_game_team` | `TeamGame` | `Team` | `many_to_one` | `team_game.team_id -> team.team_id` |
| `team_game_game` | `TeamGame` | `Game` | `many_to_one` | `team_game.game_id -> game.game_id` |
| `team_game_opponent_team` | `TeamGame` | `Team` | `many_to_one` | `team_game.opponent_team_id -> team.team_id` |
| `game_arena` | `Game` | `Arena` | `many_to_one` | `game.arena_id -> arena.arena_id` |
| `player_season_player` | `PlayerSeason` | `Player` | `many_to_one` | `player_season.person_id -> player.person_id` |
| `player_season_team_player` | `PlayerSeasonTeam` | `Player` | `many_to_one` | `player_season_team.person_id -> player.person_id` |
| `player_season_team_team` | `PlayerSeasonTeam` | `Team` | `many_to_one` | `player_season_team.team_id -> team.team_id` |
| `team_season_team` | `TeamSeason` | `Team` | `many_to_one` | `team_season.team_id -> team.team_id` |

## Current Planning Scope

Generic path resolution should currently be bounded to this live graph only.

That means current path search should assume:

- only these objects and links are in scope
- only direct and short derived paths over this graph are required
- no arbitrary deep graph traversal yet
- no many-to-many reasoning yet

## Supported Derived Paths

These are the concrete path families the live system already depends on.

### Player metric ranking

- fact object: `PlayerGame`
- row object: `Player`
- display path:
  - `PlayerGame -> Player`
- optional context path:
  - `PlayerGame -> Team`

Example:

- `Show me players by average points over the last 10 games`

### Team metric ranking

- fact object: `TeamGame`
- row object: `Team`
- display path:
  - `TeamGame -> Team`

Example:

- `Show me teams by average points over the last 10 games`

### Player object rows with attached fact metric

- row object: `Player`
- fact object: `PlayerGame`
- row path:
  - `PlayerGame -> Player`
- optional context path:
  - `PlayerGame -> Team`

Example:

- `Show me players and their total points over the last 10 games`

### Season-surface metric ranking

- fact object: `PlayerSeason` or `TeamSeason`
- row object: `Player` or `Team`
- row path:
  - `PlayerSeason -> Player`
  - `TeamSeason -> Team`

Examples:

- `Show me players by average points in the 2025-26 regular season`
- `Show me teams by wins in the 2025-26 regular season`

### Comparison over player or team fact rows

- fact object: `PlayerGame`, `TeamGame`, or a compatible season surface
- row object: `Player` or `Team`
- row path:
  - `PlayerGame -> Player`
  - `TeamGame -> Team`
- optional context path:
  - `PlayerGame -> Team`

Example:

- `Compare Brunson and Tatum average points by season type over the last 10 games`
- `Compare Lakers and Warriors average points by month over the past year`

## Current Expectation

The point of this artifact is to keep path resolution explicit:

- planning should stop choosing from a few hand-approved object branches
- planning should instead discover valid paths from this graph
- validation should prove the requested path exists
- resolution should carry the chosen path explicitly into compilation

So the live target remains:

- not `hardcoded player path`
- not `hardcoded team path`
- but `graph-bounded discovered path resolution`
