# Batch 30

## Change

Rename several `PlayerGame` fields to align more closely with natural language:

- `game_datetime_utc` -> `game_start_time_utc`
- `minutes_played_decimal` -> `minutes_played`
- `points_fast_break` -> `fast_break_points`
- `points_in_the_paint` -> `points_in_paint`
- `points_second_chance` -> `second_chance_points`

## Why

- these names are closer to how users naturally phrase basketball questions
- they reduce implementation-shaped wording like `decimal`
- they make the `PlayerGame` surface easier for prompt-to-query generation to interpret
