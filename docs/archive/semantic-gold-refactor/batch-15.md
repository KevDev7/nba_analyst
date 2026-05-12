# Semantic Gold Refactor Batch 15

This batch removes schedule ordering metadata from the public `Game` object.

## Accepted Object Decisions

### 1. Remove `game_sequence` from Game

Decision:
- remove `game_sequence` from the public `Game` surface

Why:
- `game_sequence` is schedule ordering metadata from the source feed rather than
  a strong business-facing semantic concept
- user-facing analytics questions are better served by `game_date` and
  `game_datetime_utc` than by a feed ordering number
- keeping it on `Game` adds low-value schedule metadata to the public contract

Remove from `Game`:
- `game_sequence`

Keep on `Game`:
- `game_date`
- `game_datetime_utc`
- remaining durable identity, timing, venue, and attendance context

Result:
- the public `Game` object is less tied to source schedule ordering metadata

Deferred downstream follow-up:
- trim `GAME_SCHEMA`
- update attribute inventory
- regenerate ontology and capabilities
- refresh semantic gold tests if needed
- redeploy `game` in Athena/Glue
