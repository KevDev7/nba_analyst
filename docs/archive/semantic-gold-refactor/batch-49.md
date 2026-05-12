# Batch 49

Date: 2026-04-20

## Summary

Expanded `semantic_gold.team_season` with a first wave of season-level advanced boxscore metrics derived from season totals aggregated over `TeamGame`.

## Added Fields

- `assist_percentage`
- `ast_to_turnover_ratio`
- `assist_ratio`
- `offensive_rebound_percentage`
- `defensive_rebound_percentage`
- `rebound_percentage`
- `effective_field_goal_percentage`
- `three_point_attempt_rate`
- `free_throw_attempt_rate`
- `true_shooting_percentage`

## Why

These metrics are all clean season-level formulas over team and opponent boxscore totals already available at the `TeamGame` grain, so they were a safe first expansion for `TeamSeason` without needing the additional hybrid possession or defensive shot-context inputs used by the old advanced season view.

## Implementation Notes

- derived from season totals rolled up from `semantic_gold.TeamGame`
- kept raw ratio scales for:
  - `three_point_attempt_rate`
  - `free_throw_attempt_rate`
- kept percentage scales for the remaining percentage metrics

## Deferred

Still deferred for a later `TeamSeason` wave:

- `possessions`
- `pace`
- `offensive_rating`
- `defensive_rating`
- `net_rating`
- `steal_percentage`
- `turnover_ratio`
- `block_percentage`
