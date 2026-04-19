# Semantic Gold Refactor Batch 6

This batch captures the cleanup of source-specific Basketball Reference
enrichment from the public `Player` object.

## Accepted Object Decisions

### 1. Remove BBR/source-specific fields from Player

Decision:
- keep `Player` as the canonical player object
- remove the Basketball Reference/source-specific enrichment columns from
  `semantic_gold.player`
- keep those source-explicit fields in silver/internal layers for now

Why:
- these fields are source-branded rather than clean business-facing player
  attributes
- keeping them in the public gold layer overstates source-specific enrichment as
  product-truth
- silver is the better place to preserve provenance and source-specific
  matching details until we decide which values deserve promotion into canonical
  player attributes

Remove from `Player`:
- `basketball_reference_player_id`
- `bbr_match_method`
- `bbr_match_confidence`
- `bbr_profile_url`
- `bbr_formal_name`
- `bbr_position_raw`
- `bbr_shoots`
- `bbr_height_cm`
- `bbr_weight_kg`
- `bbr_college_raw`
- `bbr_birth_country_code`
- `bbr_headshot_url`
- `bbr_hall_of_fame_flag`

Keep on `Player`:
- canonical player identity fields
- canonical bio/profile fields
- team link and lifecycle fields
- non-source-branded player dimensions

Important note:
- this batch does not delete the source data from silver
- this batch also does not yet decide which of these values may later be
  promoted back into canonical, source-agnostic `Player` attributes

Deferred downstream follow-up:
- trim `PLAYER_SCHEMA`
- update the `player` transform
- update attribute inventory
- update semantic gold tests
- review ontology/capability artifacts later for removed player attributes
- redeploy `player` in Athena/Glue
