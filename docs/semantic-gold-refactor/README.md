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
- [Batch 34](./batch-34.md)
- [Batch 35](./batch-35.md)
- [Batch 36](./batch-36.md)
- [Batch 37](./batch-37.md)
- [Batch 38](./batch-38.md)
- [Batch 39](./batch-39.md)
- [Batch 40](./batch-40.md)
- [Batch 41](./batch-41.md)
- [Batch 42](./batch-42.md)
- [Batch 43](./batch-43.md)
- [Batch 44](./batch-44.md)
- [Batch 45](./batch-45.md)
- [Batch 46](./batch-46.md)
- [Batch 47](./batch-47.md)
- [Batch 48](./batch-48.md)
- [Batch 49](./batch-49.md)
- [Batch 50](./batch-50.md)
- [Batch 51](./batch-51.md)
- [Batch 52](./batch-52.md)
- [Batch 53](./batch-53.md)
- [Batch 54](./batch-54.md)
- [Batch 55](./batch-55.md)
- [Batch 56](./batch-56.md)
- [Batch 57](./batch-57.md)
- [Batch 58](./batch-58.md)
- [Batch 59](./batch-59.md)
- [Batch 60](./batch-60.md)
- [Batch 61](./batch-61.md)
- [Batch 62](./batch-62.md)
- [Batch 63](./batch-63.md)
- [Batch 64](./batch-64.md)
- [Batch 65](./batch-65.md)
- [Batch 66](./batch-66.md)
- [Batch 67](./batch-67.md)
- [Batch 68](./batch-68.md)
- [Batch 69](./batch-69.md)
- [Batch 70](./batch-70.md)
- [Batch 71](./batch-71.md)
- [Batch 72](./batch-72.md)
- [Batch 73](./batch-73.md)
- [Batch 74](./batch-74.md)
- [Batch 75](./batch-75.md)
- [Batch 76](./batch-76.md)
- [Batch 77](./batch-77.md)
- [Batch 78](./batch-78.md)
- [Batch 79](./batch-79.md)
- [Batch 80](./batch-80.md)
- [Batch 81](./batch-81.md)
- [Batch 82](./batch-82.md)
- [Batch 83](./batch-83.md)
- [Batch 84](./batch-84.md)
- [Batch 85](./batch-85.md)
- [Batch 86](./batch-86.md)
- [Batch 87](./batch-87.md)
- [Batch 88](./batch-88.md)
- [Batch 89](./batch-89.md)
- [Batch 90](./batch-90.md)
- [Batch 91](./batch-91.md)
- [Batch 92](./batch-92.md)
- [Batch 93](./batch-93.md)
- [Batch 94](./batch-94.md)

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
