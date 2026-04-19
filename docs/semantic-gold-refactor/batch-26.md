# Batch 26

## Box score rename: clarify blocked-shot semantics

Accepted change:
- rename `blocks` to `shots_blocked`
- rename `blocks_received` to `shots_blocked_against`

Applies to:
- `PlayerGame`
- `TeamGame`

Reasoning:
- `blocks` is a common stat name, but slightly vague in a semantic schema
- `blocks_received` is understandable but awkward and less natural basketball language
- the new pair makes the direction of the stat explicit:
  - `shots_blocked` = shots blocked by the player or team
  - `shots_blocked_against` = that player or team getting shots blocked

Downstream propagation in this batch:
- update semantic_gold contract
- update player_game and team_game transforms
- update attribute inventory
- regenerate ontology and interpreter capabilities
- update semantic_gold tests
