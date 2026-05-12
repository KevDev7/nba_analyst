# Advanced Metric Formulas

This document records the formulas used by the **current supported Athena gold advanced views**.

Review note:
- reviewed against the currently deployed Athena supported-view surface on March 29, 2026
- if this file conflicts with the live deploy scripts or Athena view definitions, treat the deploy scripts as the implementation source of truth

Supported scope:
- `vw_player_season_boxscore_advanced`
- `vw_team_season_boxscore_advanced`

Removed scope:
- the old Athena-only player possession/on-court advanced view family was deleted after the Databricks-alignment work
- those removed formulas are intentionally not documented here as active warehouse behavior

If this file conflicts with the transform scripts under `pipelines/athena/transform/gold/`, treat the scripts as the implementation source of truth.

Dynamic rate note:

- player rate stats are no longer materialized as separate Athena views
- `per X minutes` output is now computed dynamically from `agg_player_season` totals and `seconds_played_total` at query time
- this keeps the warehouse surface smaller while supporting arbitrary scales such as `per 36`, `per 48`, and `per minute`

## Common Denominator Notes

- `minutes_total = seconds_played_total / 60.0`
- player played-game rule:
  - include a game when `did_play = 1` or `seconds_played_total > 0`
- team minutes display in the team advanced view:
  - `minutes = seconds_played_total / 300.0`
  - team-seconds aggregate across five players, so dividing by `300` converts team-seconds into displayed game minutes

## `vw_player_season_boxscore_advanced`

SQL source:
- [deploy_player_season_boxscore_advanced_view.py](/Users/HungNguyen/Desktop/Projects/nba_analyst/pipelines/athena/transform/gold/deploy_player_season_boxscore_advanced_view.py)

Base tables:
- `agg_player_season`
- `fct_player_game`
- `fct_team_game`
- `dim_player`

Context build:
- only the games the player actually appeared in are included
- team and opponent denominator context is aggregated from `fct_team_game` over those played games
- current player naming comes from current `dim_player`
- `agg_player_season` remains the canonical business aggregate for player-season numerators
- possession provenance, defensive shot-context provenance, and QA-supporting on-court totals are served from `vw_player_season_provenance_debug`
- possession attribution path priority is:
  - exact from `silver/possessions`
  - event-based fallback from `silver/playbyplay` plus `silver/pbpstats_event_context_v1`
  - boxscore minute-share fallback from `fct_team_game`
- defensive shot-context attribution path priority is:
  - exact from `silver/playbyplay` plus `silver/on_court_state`
  - event-based fallback from `silver/playbyplay` plus `silver/pbpstats_event_context_v1`
  - boxscore minute-share fallback from `silver/boxscore_team_game`

Display mappings:
- `player_id = agg_player_season.person_id`
- `player_name = COALESCE(dim_player.display_name, dim_player.player_name)`
- `team = agg_player_season.primary_team_abbreviation`
- `age = agg_player_season.age_on_jan_31`
- `minutes = seconds_played_total / 60.0`

Formulas:
- `ast_to_turnover_ratio`
  - `AST / TO`
- `assist_ratio`
  - `100 * AST / (FGA + 0.44 * FTA + AST + TO)`
- `offensive_rebound_percentage`
  - `100 * OREB * (team_minutes_total / 300.0) / (minutes_total * (team_oreb_total + opponent_dreb_total))`
- `defensive_rebound_percentage`
  - `100 * DREB * (team_minutes_total / 300.0) / (minutes_total * (team_dreb_total + opponent_oreb_total))`
- `rebound_percentage`
  - `100 * REB * (team_minutes_total / 300.0) / (minutes_total * (team_reb_total + opponent_reb_total))`
- `steal_percentage`
  - `100 * STL / vw_player_season_provenance_debug.defensive_possessions_total`
- `block_percentage`
  - `100 * BLK / vw_player_season_provenance_debug.opponent_two_point_attempts_while_on_court_total`
- `turnover_ratio`
  - `100 * TO / (FGA + 0.44 * FTA + AST + TO)`
- `effective_field_goal_percentage`
  - `100 * (FGM + 0.5 * 3PM) / FGA`
- `three_point_attempt_rate`
  - `3PA / FGA`
  - raw ratio on a `0-1` scale
  - rounded to `3` decimal places in the view output
  - return `NULL` when `FGA <= 0`
- `free_throw_attempt_rate`
  - `FTA / FGA`
  - raw ratio on a `0-1` scale
  - rounded to `3` decimal places in the view output
  - return `NULL` when `FGA <= 0`
- `true_shooting_percentage`
  - `100 * PTS / (2 * (FGA + 0.44 * FTA))`
- `pie`
  - numerator:
    - `PTS + FGM + FTM - FGA - FTA + DREB + (0.5 * OREB) + AST + STL + (0.5 * BLK) - PF - TO`
  - denominator:
    - the same term set summed at total-game level over each game the player appeared in
  - final value:
    - `player_numerator / denominator`
- `assist_percentage`
  - `100 * AST / (((minutes_total / (team_minutes_total / 300.0)) * team_fgm_total) - FGM)`
- `usage_percentage`
  - `100 * ((FGA + 0.44 * FTA + TO) * (team_minutes_total / 300.0)) / (minutes_total * (team_fga_total + 0.44 * team_fta_total + team_to_total))`
- `possessions`
  - `possessions_total / 2.0`
- `pace`
  - `48 * (possessions_total / 2.0) / minutes_total`
- `offensive_rating`
  - `100 * vw_player_season_provenance_debug.team_points_for_while_on_court_total / vw_player_season_provenance_debug.offensive_possessions_total`
- `defensive_rating`
  - `100 * vw_player_season_provenance_debug.team_points_against_while_on_court_total / vw_player_season_provenance_debug.defensive_possessions_total`
- `net_rating`
  - `offensive_rating - defensive_rating`

Internal provenance surface:
- player possession and shot-context provenance is intentionally not exposed on `vw_player_season_boxscore_advanced`
- inspect `vw_player_season_provenance_debug` for:
  - `possession_source_method`
  - `exact_possession_games`
  - `ot_fallback_possession_games`
  - `event_estimated_possession_games`
  - `boxscore_estimated_possession_games`
  - `missing_possession_games`
  - `possession_coverage_pct`
  - `exact_shot_context_games`
  - `event_estimated_shot_context_games`
  - `boxscore_estimated_shot_context_games`
  - `missing_shot_context_games`
  - `shot_context_coverage_pct`
  - `shot_context_source_method`

## `vw_team_season_boxscore_advanced`

SQL source:
- [deploy_team_season_boxscore_advanced_view.py](/Users/HungNguyen/Desktop/Projects/nba_analyst/pipelines/athena/transform/gold/deploy_team_season_boxscore_advanced_view.py)

Base tables:
- `agg_team_season`
- `fct_team_game`
- `dim_team`
- `silver.boxscore_team_game`

Implementation notes:
- this is a hybrid view
- `possessions`, `pace`, `turnover_ratio`, ratings, and `steal_percentage` now come from hybrid season totals materialized into `agg_team_season`
- `block_percentage` now comes from hybrid team defensive shot-context totals materialized into `agg_team_season`
- bookkeeping-heavy team ratios use season context derived from `silver.boxscore_team_game`
- internal provenance counters for possession and shot-context coverage now live in `team_season_provenance_sidecar`, not on the public `agg_team_season` surface

Display mappings:
- `team = dim_team.team_abbreviation` with `dim_team.team_name` fallback
- `games_played = games_played`
- `wins = wins`
- `losses = losses`

Formulas:
- `possessions`
  - hybrid team possessions from `agg_team_season`:
  - `possessions_total / 2.0`
  - season totals are sourced with priority:
    - exact from `silver/possessions`
    - OT fallback from `silver/possessions_ot_fallback`
    - event-estimated from `silver/playbyplay`
    - boxscore-estimated fallback
- `pace`
  - `240 * possessions / team_minutes_total`
- `offensive_rating`
  - `100 * points_for_total / possessions`
- `defensive_rating`
  - `100 * points_against_total / possessions`
- `net_rating`
  - `offensive_rating - defensive_rating`
- `assist_percentage`
  - `100 * assists_total / field_goals_made_total`
- `ast_to_turnover_ratio`
  - `assists_total / turnovers_total`
- `assist_ratio`
  - `100 * assists_total / (FGA + (0.44 * FTA) + AST + TO)`
- `offensive_rebound_percentage`
  - `100 * TeamOREB / (TeamOREB + OppDREB)`
- `defensive_rebound_percentage`
  - `100 * TeamDREB / (TeamDREB + OppOREB)`
- `rebound_percentage`
  - `100 * TeamREB / (TeamREB + OppREB)`
- `steal_percentage`
  - `100 * STL / defensive_possessions_total`
- `turnover_ratio`
  - `100 * TeamTO / possessions`
- `block_percentage`
  - `100 * BLK / opponent_two_point_attempts_total`
- `effective_field_goal_percentage`
  - `100 * (FGM + 0.5 * 3PM) / FGA`
- `three_point_attempt_rate`
  - `3PA / FGA`
  - raw ratio on a `0-1` scale
  - rounded to `3` decimal places in the view output
  - return `NULL` when `FGA <= 0`
- `free_throw_attempt_rate`
  - `FTA / FGA`
  - raw ratio on a `0-1` scale
  - rounded to `3` decimal places in the view output
  - return `NULL` when `FGA <= 0`
- `true_shooting_percentage`
  - `100 * PTS / (2 * (FGA + 0.44 * FTA))`
- `pie`
  - `(team PIE numerator / summed game-total PIE denominator across games played) * 100`

## Current SQL Sources

- player rebound percentages and PIE are now served from [deploy_player_season_boxscore_advanced_view.py](/Users/HungNguyen/Desktop/Projects/nba_analyst/pipelines/athena/transform/gold/deploy_player_season_boxscore_advanced_view.py)
- [deploy_team_season_boxscore_advanced_view.py](/Users/HungNguyen/Desktop/Projects/nba_analyst/pipelines/athena/transform/gold/deploy_team_season_boxscore_advanced_view.py)
