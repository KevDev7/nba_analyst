# Fixtures

This directory now centers on the live gold-first local development contract.

Primary local source of truth:

- `/Users/HungNguyen/Desktop/Projects/nba_analyst/fixtures/duckdb/gold_slice.duckdb`

The gold snapshot is built from Athena by:

- `/Users/HungNguyen/Desktop/Projects/nba_analyst/scripts/build_gold_slice_snapshot.py`

and loaded by:

- `/Users/HungNguyen/Desktop/Projects/nba_analyst/scripts/load_gold_snapshot.py`

The live semantic-layer contract now assumes these snapshot tables:

- `player`
- `extended_player`
- `player_game`
- `player_season`

Other fixture files can still remain here as historical artifacts or local examples, but they are no longer part of the live CLI/planner/runtime path.
