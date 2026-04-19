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
- [Batch 2](./batch-2.md)
- [Batch 3](./batch-3.md)
- [Batch 4](./batch-4.md)
- [Batch 5](./batch-5.md)
- [Batch 6](./batch-6.md)
- [Batch 7](./batch-7.md)
- [Batch 8](./batch-8.md)
- [Batch 9](./batch-9.md)
- [Batch 10](./batch-10.md)
- [Batch 11](./batch-11.md)
- [Batch 12](./batch-12.md)
- [Batch 13](./batch-13.md)
- [Batch 14](./batch-14.md)
- [Batch 15](./batch-15.md)
- [Batch 16](./batch-16.md)
- [Batch 17](./batch-17.md)
- [Batch 18](./batch-18.md)
- [Batch 19](./batch-19.md)
- [Batch 20](./batch-20.md)
- [Batch 21](./batch-21.md)
- [Batch 22](./batch-22.md)
- [Batch 23](./batch-23.md)
- [Batch 24](./batch-24.md)
- [Batch 25](./batch-25.md)
- [Batch 26](./batch-26.md)
- [Batch 27](./batch-27.md)
- [Batch 28](./batch-28.md)
- [Batch 29](./batch-29.md)
- [Batch 30](./batch-30.md)
- [Batch 31](./batch-31.md)
- [Batch 32](./batch-32.md)
- [Batch 33](./batch-33.md)

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
