# Batch 47

Date: 2026-04-20

## Summary

Reordered `semantic_gold.team_game` into a cleaner family-based public column layout.

## Why

The `TeamGame` surface had grown through multiple cleanup and enrichment passes, so the public schema order no longer reflected the conceptual shape of the object.

This batch keeps the same fields but organizes them more clearly:

- identity and game context
- outcome context
- playmaking and turnover context
- shooting families
- rebounding
- scoring-context families
- blocks and fouls

## Changes

- reordered `TEAM_GAME_SCHEMA` in `contracts.py`
- reordered the `TeamGame` row builder field layout in `transform_to_team_game_parquet.py`
- reordered the `team_game` section of `semantic_gold_attribute_inventory.json`

## Result

`TeamGame` is now easier to scan as a public object without changing its actual semantic coverage.
