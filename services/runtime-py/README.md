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
- return structured ranking, object-row, and comparison results
- feed grounded answer synthesis
