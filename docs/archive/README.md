# Docs Archive

This folder holds historical planning and batch-log documents that are useful
for context but are no longer the current operating surface for the project.

Archived groups:

- `completed-feature-plans/`: implemented feature plans retained for rationale
  and historical sequencing.
- `product-scope-history/`: completed Scope 1-4 PRDs, implementation plans, and
  early first-slice walkthrough notes.
- `semantic-gold-refactor/`: historical semantic-gold batch logs.

Current pipeline and semantic-gold behavior should be read from:

- `docs/README.md`
- `pipelines/README.md`
- `docs/pipeline-refactor-and-quality-layer-plan.md`
- `pipelines/athena/metadata/pipeline_registry.json`
- `pipelines/ingestion/source_manifest.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `pipelines/athena/transform/semantic_gold/contracts.py`
- `pipelines/athena/transform/silver/SILVER_RUNBOOK.md`
- `pipelines/athena/quality/README.md`

Reference repository clones under `/references` are research inputs only. They
are not operational ingestion code unless their logic is promoted into
`pipelines/ingestion`, registered in the pipeline registry/source manifest, and
covered by the normal pipeline checks.
