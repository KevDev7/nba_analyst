# Analysis Runtime

This doc pins down the current live runtime behavior for the one-step NBA
analyst.

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
- preserves structured ranking, aggregate, object-row, find-row, time-series,
  and comparison inputs/results
- stores the latest result in runtime state for follow-up Python analysis

## Live Plan Shapes

- SQL-only single-step plans
  - ranking/top-N
  - grouped aggregates
  - object rows
  - find rows
  - time-series trends
- SQL + Python multi-step plans
  - comparison summaries and grouped comparison breakdowns

## What Still Stays Thin

The runtime still does not try to be a full workflow engine yet.

Not implemented yet:

- chart generation
- richer artifact persistence
- broad multi-step branching beyond the current comparison-analysis path
- Python sandboxing for arbitrary generated analysis code
