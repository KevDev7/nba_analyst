# Semantic Object Roadmap

This document records the next planned semantic objects after the current
`semantic_gold` core:

- `player`
- `team`
- `arena`
- `game`
- `player_game`
- `team_game`
- `player_season`
- `player_season_team`
- `team_season`

It is intentionally a roadmap artifact, not an implementation contract. The
goal is to make the future object surface explicit early so ontology work does
not drift away from the expected warehouse expansion path.

## Why This Exists

This roadmap is meant to reduce refactor risk by making the next semantic object
batches visible before they are implemented.

It does not mean these objects must all be built immediately.

It does mean:

- ontology changes should anticipate these business objects
- `semantic_gold` expansion should follow these object seams
- new slices should avoid introducing assumptions that would make these objects
  awkward to add later

## Current Live Surface

The current live semantic objects are:

- `Player`
- `Team`
- `Arena`
- `Game`
- `PlayerGame`
- `TeamGame`
- `PlayerSeason`
- `PlayerSeasonTeam`
- `TeamSeason`

## Shipped Season Object Batch

### `PlayerSeason`

Status:
- shipped semantic object

Why it matters:
- users naturally ask season-level questions about players
- it is the clean semantic home for season aggregates that should not be
  recomputed ad hoc from `PlayerGame` every time
- it gives the ontology a true player-season grain instead of forcing season
  questions through game-level facts

Expected grain:
- one row per `(person_id, season_year, season_type)`

Backing surface:
- `semantic_gold.player_season`

Current core links:
- `PlayerSeason -> Player`

Current dimensions include:
- `person_id`
- `season_year`
- `season_type`

Current measures include:
- season totals
- season averages
- season rates
- season games played

### `PlayerSeasonTeam`

Status:
- shipped semantic object

Why it matters:
- users ask about player production for a specific team in a season
- it handles multi-team player seasons without forcing one ambiguous season row
- it is the clean home for team-filtered player season object outputs

Expected grain:
- one row per `(person_id, team_id, season_year, season_type)`

Backing surface:
- `semantic_gold.player_season_team`

Current core links:
- `PlayerSeasonTeam -> Player`
- `PlayerSeasonTeam -> Team`

Current dimensions include:
- `person_id`
- `team_id`
- `season_year`
- `season_type`
- team stint context

Current measures include:
- season-team totals
- season-team per-game metrics
- season-team advanced/rate fields where supported

### `TeamSeason`

Status:
- shipped semantic object

Why it matters:
- team-level season questions are a first-class business concept
- it provides a proper semantic surface for standings-like and season-summary
  questions without forcing everything through `TeamGame`
- it gives the ontology a clean home for season-level team metrics

Expected grain:
- one row per `(team_id, season_year, season_type)`

Backing surface:
- `semantic_gold.team_season`

Current core links:
- `TeamSeason -> Team`

Current dimensions include:
- `team_id`
- `season_year`
- `season_type`

Current measures include:
- wins
- losses
- win percentage
- season scoring
- assists, rebounds, steals, blocks, fouls, turnovers, shooting totals, per-game
  metrics, percentages, and other populated public season measures

## Later Supporting Objects

### `Season`

Priority:
- later foundational object

Why it matters:
- users ask about seasons as real business entities
- it gives a canonical home for reusable season metadata
- it reduces repeated handling of season identity across `Game`,
  `PlayerSeason`, and `TeamSeason`

Expected grain:
- one row per canonical NBA season

Likely backing surface:
- future `semantic_gold.season`

Likely dimensions:
- canonical season key
- `season_year`
- display label
- start date
- end date
- current / closed status

Likely core links:
- `Game -> Season`
- `PlayerSeason -> Season`
- `TeamSeason -> Season`

Design note:
- once `Season` exists, `season_year` should increasingly be treated as a
  season attribute rather than the only season identity concept

### `SeasonType`

Priority:
- later small semantic object

Why it matters:
- users ask about concepts like playoffs and regular season as real business
  concepts, not just enum values
- it gives a governed home for aliases and ordering
- it helps prevent ad hoc handling of `playoffs`, `regular season`, `play-in`,
  and other competition phases

Expected grain:
- one row per canonical competition phase / season type

Likely backing surface:
- future `semantic_gold.season_type`

Likely dimensions:
- canonical season type key
- display label
- aliases
- ordering

Likely core links:
- `Game -> SeasonType`
- `PlayerSeason -> SeasonType`
- `TeamSeason -> SeasonType`
- `Season -> SeasonType` only if the future model needs that relationship

Design note:
- this is intentionally a smaller object than `Season`

### `Date`

Priority:
- later supporting object

Why it matters:
- reusable time semantics eventually become important across multiple objects
- a `Date` object can centralize day / month / year / quarter / weekday logic
- it can support richer trend analysis without every object carrying its own
  independent derived time rules forever

Expected grain:
- one row per calendar date

Likely backing surface:
- future `semantic_gold.date`

Likely dimensions:
- canonical date key
- calendar date
- day
- month
- year
- quarter
- weekday
- month label

Likely core links:
- `Game -> Date`
- later time-based links from other objects where appropriate

Design note:
- until this object exists, derived time attributes such as `game_year_month`
  are acceptable semantic bridges

## Recommended Sequence

Recommended order of expansion:

1. `PlayerSeason`
2. `TeamSeason`
3. `Season`
4. `SeasonType`
5. `Date`

Why this order:

- `PlayerSeason` and `TeamSeason` unlock the largest next jump in business
  question coverage
- `Season` becomes more valuable once season-grain objects exist
- `SeasonType` and `Date` are important, but they support broader semantic depth
  more than they unlock the next highest-value object grains by themselves

## Guardrails

When adding these objects later:

- preserve clean business object names in `semantic_gold`
- define explicit grain first
- define public attributes with ontology roles
- define links explicitly
- avoid introducing warehouse-only lineage fields into the public surface
- prefer additive ontology growth over slice-specific shortcuts
