# Batch 94

## Summary
- completed the advanced `player_season_team` Bucket 3 surface so the team-stint season object now exposes possession totals, ratings, advanced percentages, and shooting efficiency fields already supported by the underlying transform
- aligned the supporting schema surfaces with that expanded contract:
  - semantic gold schema tests
  - transform tests
  - semantic gold attribute inventory
  - refactor index

## Added To `player_season_team`
- `offensive_possessions_total`
- `defensive_possessions_total`
- `possessions`
- `pace`
- `offensive_rating`
- `defensive_rating`
- `net_rating`
- `assist_to_turnover_ratio`
- `assist_percentage`
- `usage_percentage`
- `offensive_rebound_percentage`
- `defensive_rebound_percentage`
- `rebound_percentage`
- `steal_percentage`
- `block_percentage`
- `effective_field_goal_percentage`
- `three_point_attempt_rate`
- `free_throw_attempt_rate`
- `true_shooting_percentage`

## Notes
- no new silver-layer work was required
- the stint grain remains one row per `(person_id, team_id, season_year, season_type)`
- advanced fields continue to use the same existing on-court context sidecars as `player_season`, but are aggregated only over the games for that player's specific team stint
