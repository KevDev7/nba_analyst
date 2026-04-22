# Batch 31

## Change

Rename the public `Game` timestamp field:

- `game_datetime_utc` -> `game_start_time_utc`

## Why

- `game_start_time_utc` reads more naturally for users
- it makes the meaning explicit: this is the game start timestamp
- it aligns the `Game` object with the more human-like naming direction of the refactor

## Notes

- this change is scoped to the public `Game` object
- `PlayerGame` and `TeamGame` were updated internally to keep reading the shared game timestamp context correctly
