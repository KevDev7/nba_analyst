# Semantic Gold Refactor Batch 7

This batch captures the next cleanup of feed-shaped fields from the public
`PlayerGame` object.

## Accepted Object Decisions

### 1. Remove feed-specific player row metadata from PlayerGame

Decision:
- keep `PlayerGame` as the player-in-game fact object
- remove feed-shaped player row metadata that does not belong on the public
  semantic surface

Why:
- these fields describe source feed presentation or ephemeral row metadata more
  than stable player-in-game business facts
- they do not materially improve the public semantic contract
- keeping them in `semantic_gold.player_game` makes the object feel more
  feed-shaped than product-shaped

Remove from `PlayerGame`:
- `player_position`
- `player_status`
- `player_order`

Keep on `PlayerGame`:
- the natural grain keys:
  - `game_id`
  - `person_id`
- the team link:
  - `team_id`
- the actual participation/context fields:
  - `team_side`
  - `is_starter`
  - `is_on_court`
  - `did_play`
- all box-score and scoring measures

Important note:
- `player_position` was intended as a game-row position label from the source
  feed, not the canonical player profile position
- `player_status` was intended as a game-row availability/participation label
  from the feed
- `player_order` was explicitly source feed ordering metadata
- of the three, `player_order` was the clearest non-semantic field, but the
  batch removes all three for a cleaner public object boundary

### 2. Rename plus/minus measure to a cleaner public name

Decision:
- rename `plus_minus_points` to `plus_minus` on `PlayerGame`

Why:
- `plus_minus` is the normal basketball-facing name
- the old name was technically precise but unnecessarily awkward as a public
  semantic measure

Rename on `PlayerGame`:
- `plus_minus_points` -> `plus_minus`

Deferred downstream follow-up:
- trim `PLAYER_GAME_SCHEMA`
- update the `player_game` transform
- update attribute inventory
- regenerate ontology and capabilities
- update semantic gold tests
- redeploy `player_game` in Athena/Glue
