# Batch 23

## Player cleanup: remove low-value status and lifecycle helper fields

Accepted change:
- remove `latest_status` from `Player`
- remove `first_seen_game_date` from `Player`
- remove `last_seen_game_date` from `Player`

Reasoning:
- these are niche helper fields rather than core player identity or common semantic context
- they are derivable if needed once sandbox-backed analysis exists
- removing them keeps `Player` more focused on identity, role, bio, and team linkage

Keep on `Player`:
- `person_id`
- `full_name`
- `first_name`
- `last_name`
- `primary_position`
- `position_group`
- `latest_team_id`
- `latest_jersey_number`
- `first_season_played`
- `last_season_played`
- `birth_date`
- `school`
- `country`
- `height_inches`
- `weight_lbs`
- `draft_year`
- `draft_round`
- `draft_number`

Downstream propagation in this batch:
- update semantic_gold contract
- update player transform
- update attribute inventory
- regenerate ontology and interpreter capabilities
- update semantic_gold tests
