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

Navigation aids:

- `athena/metadata/pipeline_registry.json`
  - curated map of raw, silver, gold, semantic gold, and serving artifacts
  - includes each artifact's grain, source keys, destination key, entrypoint, dependencies, heavy-runtime flag, checkpoint key, and schema owner where known
- `ingestion/source_manifest.py`
  - renders the raw/bronze source map from the registry
  - declares the shared game- and season-scoped backfill window used by quality checks
- `athena/transform/silver/SILVER_RUNBOOK.md`
  - current silver runner model, heavy-table checkpoint behavior, and targeted backfill commands
- `athena/quality/README.md`
  - current quality-layer datasets, Athena registration behavior, and parity/reconciliation commands

Operational command map:

```bash
# raw / bronze source ownership and expected backfill seasons
python3 pipelines/ingestion/source_manifest.py

# silver pipeline
python3 pipelines/athena/transform/silver/run_silver_pipeline.py
python3 pipelines/athena/transform/silver/run_silver_pipeline.py --include-heavy

# quality baseline and parity locks
python3 pipelines/athena/quality/run_quality_baseline.py
python3 pipelines/athena/quality/gold_parity_lock.py
python3 pipelines/athena/quality/silver_gold_reconciliation.py
python3 pipelines/athena/quality/serving_parity_lock.py

# serving snapshot
python3 -m pipelines.athena.serving.duckdb.build_serving_snapshot
```

Docs rule of thumb:

- The current operational truth lives in this README, the registry, the source
  manifest, the silver runbook, the quality README, and the active transform
  scripts.
- Long-form plans under `docs/` are useful project history, but they are not
  operational contracts unless this README points to them.
- Historical batch logs and superseded plans belong under `docs/archive/`.

Migration intent:

- `nba_analyst` is now the source of truth for the product
- schema, ontology, snapshot generation, and planner/runtime assumptions should evolve together here
- the old repo no longer owns pipeline evolution

Serving snapshot ownership:

- `pipelines/athena/serving/duckdb/` owns the pipeline serving snapshot built
  from Athena contract sources into `data/serving/nba_serving.duckdb`.
- `scripts/build_gold_slice_snapshot.py` and `scripts/load_gold_snapshot.py`
  remain the app-facing semantic-gold development snapshot path used by the
  assistant runtime and fast tests.
- Both paths are currently supported because they expose different contracts.
  Consolidation should only happen after the app runtime is moved to the
  pipeline serving contract or the pipeline builder is narrowed to the semantic
  app contract.
