# Semantic Gold Refactor

This folder tracks `semantic_gold` object-model refactor work.

Purpose:
- reshape `semantic_gold` objects first
- record accepted schema/object decisions cleanly
- defer broader downstream propagation until a meaningful batch of object changes is stable

Working rule:
- during this phase, the intended `semantic_gold` object model is the source of truth
- downstream code should not drive schema decisions
- after a batch is stable, propagate changes to the rest of the system

## Batches

- [Batch 1](./batch-1.md)

## Deferred Downstream Follow-Up

When a batch is ready to propagate, update:
- `pipelines/athena/transform/semantic_gold/contracts.py`
- semantic gold transform scripts
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json`
- `scripts/generate_semantic_ontology.py`
- `fixtures/ontology/semantic-gold.yaml`
- `fixtures/interpreter/semantic-capabilities.json`
- semantic gold tests
- planner/runtime/query-model assumptions that depend on the old object shape
