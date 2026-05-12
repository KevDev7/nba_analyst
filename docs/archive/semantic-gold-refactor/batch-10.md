# Semantic Gold Refactor Batch 10

This batch completes the cleanup of duplicated season helper fields anywhere
the public semantic object already exposes the canonical season fields.

## Accepted Object Decisions

### 1. Remove duplicated season helper fields from remaining season-aware objects

Decision:
- remove `raw_season_type_code` from every remaining public `semantic_gold`
  object that already has `season_type`
- remove `season_start_year` from every remaining public `semantic_gold`
  object that already has `season_year`

Objects cleaned in this batch:
- `Game`
- `PlayerGame`
- `PlayerSeason`
- `PlayerSeasonTeam`

Why:
- `season_type` is already the canonical semantic field
- `raw_season_type_code` is a source-shaped helper rather than a business-facing
  semantic attribute
- `season_year` is already the canonical season identity field
- `season_start_year` is derivable from `season_year` and adds a second
  competing season identity field on the same public object
- carrying these helpers creates redundant season semantics on the same public
  object
- the schema is cleaner when season-aware objects expose one canonical season
  type field and one canonical season identity field

Remove from:
- `Game`
- `PlayerGame`
- `PlayerSeason`
- `PlayerSeasonTeam`

Keep:
- `season_type`
- `season_year`

Result:
- no public `semantic_gold` object now exposes both `season_type` and
  `raw_season_type_code`
- no public `semantic_gold` object now exposes both `season_year` and
  `season_start_year`

Deferred downstream follow-up:
- trim schemas
- update transforms that still carried the raw helper through
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy affected Athena/Glue tables
