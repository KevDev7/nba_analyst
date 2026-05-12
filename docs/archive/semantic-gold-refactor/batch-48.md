# Batch 48

Date: 2026-04-20

## Summary

Renamed the `TeamGame` blocked-shot pair to the shorter mirrored stat names:

- `blocks`
- `opponent_blocks`

## Why

`TeamGame` now uses a broad mirror pattern across core stat families:

- `assists` / `opponent_assists`
- `steals` / `opponent_steals`
- `turnovers` / `opponent_turnovers`

Using `blocks` / `opponent_blocks` keeps the table more internally consistent than the older blocked-shot naming pair.

## Changes

- renamed the `TeamGame` public contract fields
- updated the `TeamGame` transform output keys
- updated attribute inventory and tests

## Note

While doing this, the `PlayerGame` contract metadata was restored to the previously agreed naming pair:

- `blocks`
- `opponent_blocks`

That keeps `PlayerGame` and `TeamGame` intentionally different, matching their different semantic tradeoffs.
