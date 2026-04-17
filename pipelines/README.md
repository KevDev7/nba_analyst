# Pipelines

This folder is now the home for the data pipeline code that used to live in the old lakehouse repo.

Current top-level areas:

- `athena/`
  - silver and gold transforms
  - metadata and data dictionaries
  - DuckDB serving snapshot builders
  - pipeline tests
- `ingestion/`
  - raw-source backfills and ingestion utilities

Migration intent:

- `nba_analyst` is now the source of truth for the product
- schema, ontology, snapshot generation, and planner/runtime assumptions should evolve together here
- the old repo no longer owns pipeline evolution

Important note:

- there is still some duplication to reconcile between the migrated pipeline snapshot builders under `pipelines/athena/serving/duckdb/` and the app-facing gold snapshot scripts under `scripts/`
- that is now an in-repo consolidation problem, not a cross-repo problem
