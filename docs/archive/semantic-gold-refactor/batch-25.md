# Batch 25

## PlayerGame cleanup: remove live-state and redundant duration helper fields

Accepted change:
- remove `is_on_court` from `PlayerGame`
- remove `seconds_played_total` from `PlayerGame`

Reasoning:
- `is_on_court` is live-state style feed metadata rather than durable postgame player-game semantics
- `seconds_played_total` is redundant once `minutes_played_decimal` already exists
- season aggregates can still derive `games_played` safely from `did_play` and `minutes_played_decimal`

Keep on `PlayerGame`:
- identity and link keys
- game time and season context
- `is_starter`
- `did_play`
- `minutes_played_decimal`
- the box score measures

Downstream propagation in this batch:
- update semantic_gold contract
- trim player_game transform output
- update player season aggregate helpers
- update attribute inventory
- regenerate ontology and interpreter capabilities
- update semantic_gold tests
