# Analysis Runtime

This doc pins down the live runtime behavior after vertical slice 4.

## Input

- a validated execution plan from the Haskell semantic core

## Data Backend

The live local backend now uses:

- DuckDB
- gold-derived snapshot data from `fixtures/duckdb/gold_slice.duckdb`

## Runtime Responsibilities

The runtime now:

- ensures the gold snapshot exists locally
- executes SQL plans over the gold snapshot
- preserves structured ranking rows, object rows, and comparison inputs
- stores the latest result in runtime state for follow-up Python analysis

## Live Plan Shapes

- SQL-only single-step plans
  - total-points ranking
  - average-points ranking
  - player-row object query
- SQL + Python multi-step plans
  - player comparison over recent games

## What Still Stays Thin

The runtime still does not try to be a full workflow engine yet.

Not implemented yet:

- chart generation
- richer artifact persistence
- broad multi-step branching beyond the comparison path
