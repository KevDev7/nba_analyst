# Semantic Gold Refactor Batch 8

This batch captures the cleanup of low-value duplicated season metadata from the
public `TeamSeason` object.

## Accepted Object Decisions

### 1. Remove low-value source and helper fields from TeamSeason

Decision:
- keep `TeamSeason` as the team-in-season aggregate object
- remove `raw_season_type_code` and `average_points` from the public
`TeamSeason` surface

Why:
- `raw_season_type_code` is a source-shaped helper field rather than a clean
  business-facing season attribute
- `average_points` is better treated as a semantic metric than a materialized
  public `TeamSeason` column
- `season_start_year` is derivable from `season_year` and adds a second,
  potentially confusing season identity field to the public object
- `TeamSeason` already has the canonical season identity fields it needs:
  - `season_year`
  - `season_type`
  - `season_start_year`
- keeping both helper fields on the public aggregate object adds noise without
  improving the semantic contract

Remove from `TeamSeason`:
- `raw_season_type_code`
- `average_points`
- `season_start_year`

Keep on `TeamSeason`:
- `team_id`
- `season_year`
- `season_type`
- `games_played`
- `wins`
- `losses`
- `win_percentage`

Important note:
- this batch only trims `TeamSeason`
- it does not make a global decision about every remaining use of
  `raw_season_type_code` elsewhere in `semantic_gold`

Deferred downstream follow-up:
- trim `TEAM_SEASON_SCHEMA`
- update the `team_season` transform
- update attribute inventory
- regenerate ontology and capabilities
- update semantic gold tests if needed
- redeploy `team_season` in Athena/Glue
