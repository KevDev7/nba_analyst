# Future Gold Column Candidates

This note captures high-signal columns and surfaces observed in the current silver layer that could be promoted into the gold layer in a future pass.

Date of review: April 7, 2026

Scope:
- This is intentionally a shortlist, not a full silver-to-gold diff.
- The goal is to capture additions that look genuinely useful for product/querying.
- If a concept really wants its own table at a new grain, it is noted separately rather than forced into an existing gold table.

## Shortlist

### 1. Player-game advanced context

Why it stands out:
- We already have strong player-season advanced surfaces in gold.
- We do not yet have an equivalent player-game advanced surface.
- The silver inputs are already canonical and provenance-aware.

Recommended source tables:
- `silver/player_game_possession_context`
- `silver/player_game_defensive_shot_context`

Best candidate columns:
- `offensive_possessions`
- `defensive_possessions`
- `possessions_total`
- `team_points_for_while_on_court`
- `team_points_against_while_on_court`
- `opponent_two_point_attempts_while_on_court`
- `possession_source_method`
- `shot_context_source_method`

Likely gold target:
- new table or view at player-game grain
- likely better as a new player-game advanced surface than as extra columns directly on `fct_player_game`

Why this is valuable:
- enables game-level advanced player queries without forcing the app to reconstruct season math backwards
- aligns well with the existing player-season advanced philosophy

### 2. Additional team-game context metrics

Why it stands out:
- These are official game-summary fields already present at the same grain as `fct_team_game`.
- They are clean additions and do not require a new grain.

Recommended source table:
- `silver/boxscore_team_game`

Best candidate columns for `fct_team_game`:
- `leadChanges`
- `timesTied`
- `biggestLead`
- `biggestScoringRun`
- `fieldGoalsEffectiveAdjusted`
- `assistsTurnoverRatio`
- `reboundsTeam`
- `reboundsTeamOffensive`
- `reboundsTeamDefensive`

Suggested gold names:
- `lead_changes`
- `times_tied`
- `biggest_lead`
- `biggest_scoring_run`
- `field_goals_effective_adjusted`
- `assists_turnover_ratio`
- `rebounds_team`
- `rebounds_team_offensive`
- `rebounds_team_defensive`

Why this is valuable:
- improves direct team-game querying
- gives cleaner inputs for future team-game or team-season derived metrics

Follow-up discovered from semantic assistant testing:
- Current local semantic snapshots only have reliable `team_game` scoring fields
  such as `score`, `opponent_score`, and `point_differential`.
- Team-game boxscore detail fields such as assists, rebounds, steals, blocks,
  and many shooting/rebound columns are currently empty in `team_game`, and
  their `team_season` rollups become zero/empty as a result.
- A later profile of the local DuckDB semantic snapshot showed the same broader
  issue: `TeamGame` has many measure columns in the contract, but only a small
  scoring/possession/rating subset has real populated signal. `TeamSeason` also
  has far fewer reliable populated measures than the contract shape suggests.
- This is a data-quality / semantic-gold completeness problem, not an assistant
  planning problem. The ontology should not expose broad team-grain metrics until
  the underlying `team_game` and `team_season` values are actually populated.
- Likely root cause: `semantic_gold/transform_to_team_game_parquet.py` reads
  those fields from rows built with the narrower `TEAM_GAME_REQUIRED_COLUMNS`
  imported from the gold `fct_team_game` transform, so fields like `assists`
  and `reboundsTotal` are not present when the semantic row builder asks for
  them.

Later fix:
- Make the semantic-gold team-game transform source its team boxscore measures
  from `silver/boxscore_team_game` or from the richer gold team-game inputs,
  instead of relying on the minimal `fct_team_game` required-column list.
- After that, regenerate `semantic_gold.team_game`,
  `semantic_gold.team_season`, the local DuckDB snapshot, and the ontology so
  team-grain questions like "points, assists, and rebounds by team" are
  answerable because the data exists, not because the assistant falls back to a
  player-grain workaround.
- Once those team-game and team-season measure columns are populated with real
  signal, expose them as ontology metrics through the normal metric-generation
  path. The long-term goal is broad team-grain metric coverage from the semantic
  contract, not one-off assistant fixes for individual questions.
- Add a data-quality check that fails or warns when a semantic-gold measure
  column exists in the contract but is entirely null or constant-zero in the
  generated snapshot. This would catch the `TeamGame` / `TeamSeason` issue before
  it leaks into ontology generation or assistant behavior.

### 3. Structured birthplace fields for players

Why it stands out:
- Gold currently exposes raw birthplace text, which is useful but not query-friendly.
- Structured birthplace columns would make player-profile questions easier for SQL and for the app layer.

Current gold state:
- `extended_player_dim.bbr_birth_place_raw`
- `extended_player_dim.bbr_birth_country_code`

Potential future columns:
- `birth_city`
- `birth_state_region`
- `birth_country`

Likely gold target:
- `extended_player_dim`

Why this is valuable:
- improves filtering and grouping for player origin questions
- avoids repeated string parsing in app-side or query-time logic

## Worth Considering Later, But Not Simple Column Promotions

These are promising concepts, but they likely want their own gold surfaces rather than extra columns on an existing table.

### `silver/boxscore_game_official`

Why not a simple column promotion:
- the grain is `(gameId, personId)` for officials
- that does not fit existing supported gold tables cleanly

Likely future shape:
- a new `fct_game_official` style gold table

### `silver/boxscore_team_period`

Why not a simple column promotion:
- period grain does not fit `fct_team_game`

Likely future shape:
- a new team-period gold fact

### `silver/player_movement`

Why not a simple column promotion:
- transaction grain is very different from the current game/season gold surfaces

Likely future shape:
- a separate player transaction / movement gold surface

## Not Recommended For Simple Promotion

### Raw event and projection detail from play-by-play

Examples:
- raw `description`
- raw `qualifiers`
- event linkage fields
- many event-family booleans from `silver/playbyplay` or `silver/event_projection_v2`

Why not recommended:
- these are event-grain concepts
- adding them to current game- or season-grain gold tables would be awkward and misleading

If we ever expose them in gold:
- they should likely come through an event-grain model or a dedicated serving view

## Deferred semantic_gold Candidates

These are worth revisiting in a later semantic pass, but they were deferred from
the current implementation wave because they need more definition discipline or
clearer denominator logic.

### `semantic_gold.team_season`

#### `strength_of_schedule`

Why it is deferred:
- high-value team season context
- but more definition-dependent than the current advanced stats
- should only be added once the exact business definition is agreed

Open question:
- what canonical schedule-strength formula should the product use?

#### `turnover_percentage`

Why it is deferred:
- strong basketball concept
- but it should not be treated as equivalent to the already-added
  `turnover_ratio`
- likely needs a more specific plays-based denominator rather than the current
  possession-based path

Open question:
- which denominator should be treated as canonical for the semantic surface?

### `semantic_gold.player_game`

#### non-playing player-game rows

Why it is deferred:
- the current semantic direction is to treat `PlayerGame` as actual on-court
  participation rather than every source roster-status row
- but there is still product value in later handling the excluded non-playing
  cases explicitly

Later cases to handle:
- dressed but never entered
- inactive / unavailable
- bench DNP rows

Open question:
- should these eventually live as a normalized participation-status dimension on
  `PlayerGame`, or as a separate status-oriented semantic object/surface?

## Summary Recommendation

If we pick only a few future gold promotions, the best next candidates are:

1. player-game advanced context columns via a new player-game advanced surface
2. team-game context columns added to `fct_team_game`
3. structured birthplace columns added to `extended_player_dim`
