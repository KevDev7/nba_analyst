# Semantic Gold Refactor Batch 17

This batch removes low-value metadata flags from the public `Game` object.

## Accepted Object Decisions

### 1. Remove `league_id` and `is_sellout` from Game

Decision:
- remove `league_id` from the public `Game` surface
- remove `is_sellout` from the public `Game` surface

Why:
- `league_id` adds little semantic value for the current product because the
  data surface is already scoped to NBA analytics
- `is_sellout` is real data, but low-frequency and not central to the main
  analytics questions this product is optimizing for
- both fields add metadata breadth without materially improving grounded query
  coverage

Remove from `Game`:
- `league_id`
- `is_sellout`

Keep on `Game`:
- core game identity and timing
- venue and matchup links
- the more meaningful postgame facts that remain, such as `duration_minutes`
  and `attendance`

Result:
- the public `Game` object is even more focused on the smallest set of durable
  game semantics that are likely to matter for user questions

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
