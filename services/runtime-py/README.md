# Analysis Runtime

This service owns execution and analysis work that should not live inside the model context window.

Primary responsibilities:

- run queries
- persist intermediate artifacts
- execute Python/statistical analysis
- shape supporting outputs for the final answer

Initial implementation target:

- Python

Current live responsibility:

- execute the gold-snapshot execution plans in DuckDB
- return structured ranking, aggregate, object-row, find-row, time-series, and
  comparison results
- run the current Python comparison analysis step when a plan requires it
- feed grounded answer synthesis
