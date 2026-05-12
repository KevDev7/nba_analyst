# Semantic Gold Refactor Batch 9

This batch captures the cleanup of duplicated raw season metadata from the
public `TeamGame` object.

## Accepted Object Decisions

### 1. Remove redundant season, side, result, and low-value game-state helper fields from TeamGame

Decision:
- keep `TeamGame` as the team-in-game fact object
- remove `raw_season_type_code`, `season_start_year`, `is_home_team`,
  `is_in_bonus`, `timeouts_remaining`, `is_tie`, `is_win`, and `is_loss`
  from the public `TeamGame` surface
- replace the redundant win/loss flags with a single `game_result`
  dimension carrying `win` or `loss`

Why:
- `season_type` is already the clean semantic field
- `raw_season_type_code` is source-shaped and redundant at the public semantic
  layer
- `season_start_year` is derivable from `season_year` and creates a second
  season identity field on the same object
- `is_home_team` is just a boolean projection of `team_side`, so keeping both
  duplicates the same home/away meaning in two formats
- `is_in_bonus` is low-value transient game-state feed context that is not
  important enough for the public semantic object surface
- `timeouts_remaining` is another transient feed-state helper that adds little
  semantic value to the public object
- `is_tie` is effectively dead weight for NBA game results and adds little
  value to the public semantic object
- `is_win` and `is_loss` duplicate one semantic concept in two warehouse-style
  integer flags
- `game_result` is clearer for the chatbot and keeps the outcome as one
  expressive semantic dimension
- carrying all eight helper fields creates redundant or low-value noise on the
  same object

Remove from `TeamGame`:
- `raw_season_type_code`
- `season_start_year`
- `is_home_team`
- `is_in_bonus`
- `timeouts_remaining`
- `is_tie`
- `is_win`
- `is_loss`

Keep on `TeamGame`:
- `season_year`
- `season_type`
- `team_side`
- `game_result`
- the game/team identity fields
- the team-game measures

Important note:
- this batch only trims `TeamGame`
- it does not yet remove `raw_season_type_code` from every remaining
  `semantic_gold` object

Deferred downstream follow-up:
- trim `TEAM_GAME_SCHEMA`
- update the `team_game` transform
- update attribute inventory
- regenerate ontology and capabilities
- update semantic gold tests if needed
- redeploy `team_game` in Athena/Glue
