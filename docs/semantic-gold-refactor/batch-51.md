# Batch 51

Date: 2026-04-20

## Summary

Scoped `semantic_gold.player_game` down to actual player participation only.

## Change

`PlayerGame` now filters out source rows where `did_play` is not true.

That means the semantic object no longer includes:

- dressed but never entered
- inactive / unavailable
- bench DNP rows

## Why

The current `PlayerGame` product scope is actual on-court game participation.

Keeping non-playing roster-status rows in the same object makes player-game
questions and aggregates harder to reason about because zero-minute rows mix
participation with non-participation semantics.

## Deferred

Later handling for excluded non-playing player-game rows is tracked in:

- [future_gold_column_candidates.md](/Users/HungNguyen/Desktop/Projects/nba_analyst/pipelines/athena/metadata/future_gold_column_candidates.md)
