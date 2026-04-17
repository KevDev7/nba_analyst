# Gold Data Dictionary Notes

## `agg_team_season`

### `in_bonus_count`

- Revisit `in_bonus_count` before exposing it in user-facing product surfaces.
- Current implementation is a season sum of the single `inBonus` value captured on each team-game boxscore row from the CDN boxscore payload.
- That does not clearly represent quarter-level bonus frequency or a polished season basketball stat, so the metric is likely too implementation-shaped in its current form.
