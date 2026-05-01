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
- Earlier local semantic snapshots only had reliable `team_game` scoring fields
  such as `score`, `opponent_score`, and `point_differential`; broader team-game
  boxscore fields such as assists, rebounds, steals, and blocks were empty.
- That data-quality issue has since been fixed in the local DuckDB semantic
  snapshot. As of the latest metric-quality audit, `TeamGame` has 76 populated
  public measure columns and `TeamSeason` has 65 populated public measure
  columns.
- The ontology now exposes populated, non-rate TeamGame boxscore metrics through
  the normal metric-generation path. This includes team-grain metrics such as
  assists, rebounds, steals, blocks, shooting makes/attempts, fouls, turnovers,
  and opponent mirrors.
- `TeamSeason` now exposes all populated public measure columns as season-grain
  identity metrics.
- Planner/runtime regression now verifies the expanded metric surface end to
  end through Haskell planning, Python execution, and answer formatting. Covered
  examples include TeamGame assists/rebounds aggregates, TeamGame rebound
  rankings, TeamSeason assist rankings, TeamSeason multi-metric object output,
  and find-row display of TeamGame assists/rebounds.
- `TeamGame` rate, percentage, pace, and ratio fields remain intentionally
  deferred from metric exposure until their scale/formula semantics are audited.
  Current examples include `pace`, `field_goals_percentage`,
  `true_shooting_percentage`, and `assist_to_turnover_ratio`.

Current guardrail:
- Run `python3 scripts/audit_semantic_metric_quality.py` to inspect exposed,
  deferred, missing-data, and unexpected-unexposed metric columns.
- Run `python3 scripts/audit_semantic_metric_quality.py --fail-on-unexpected`
  in future data/ontology refreshes to catch populated exposure-ready measures
  that are not actually exposed through ontology metrics.
- Run `python3 -m unittest tests.test_team_metric_runtime_regression` after
  ontology refreshes that change team metric exposure.

Later fix:
- Audit the deferred `TeamGame` rate, percentage, pace, and ratio fields for
  scale consistency and formula correctness.
- Once those deferred fields have clear semantics, expose them as ontology
  metrics through the normal metric-generation path rather than one-off assistant
  fixes.
- Keep the metric-quality audit in the semantic refresh loop so a future
  `TeamGame` / `TeamSeason` population regression is caught before it leaks into
  assistant behavior.

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
