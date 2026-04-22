# Batch 54

Date: 2026-04-20

Scope:
- rename the team season assist-turnover field to a more human-readable public name

Changes:
- renamed on `semantic_gold.team_season`:
  - `ast_to_turnover_ratio` -> `assist_to_turnover_ratio`

Notes:
- kept this scoped to `semantic_gold`
- did not rename legacy gold advanced views or downstream percentile pipelines in this batch
