# Batch 24

## Player cleanup: remove derived season-lifecycle helper fields

Accepted change:
- remove `first_season_played` from `Player`
- remove `last_season_played` from `Player`

Reasoning:
- these are derivable lifecycle helpers rather than core player identity
- they are lower-value public dimensions once sandbox-backed analysis exists
- removing them keeps `Player` focused on stable identity, role, team linkage, and bio context

Keep on `Player`:
- `person_id`
- `full_name`
- `first_name`
- `last_name`
- `primary_position`
- `position_group`
- `latest_team_id`
- `latest_jersey_number`
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
- simplify player transform
- update attribute inventory
- regenerate ontology and interpreter capabilities
- update semantic_gold tests
