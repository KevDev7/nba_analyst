# Answer Synthesis

This doc pins down the live answer-synthesis behavior.

## Input

- structured runtime results
- planning metadata:
  - metric used
  - time window used
  - result limit
  - assumptions, if any

## Output

The live synthesis layer should produce:

- a short written summary
- a ranked table

## Rules

Answer synthesis should:

- stay fully grounded in runtime output
- mention the metric and time window used
- include assumptions when aliases or synonyms were interpreted
- avoid inventing any analysis not present in runtime results

## LLM Usage

The live slices do not require a live LLM yet.

The synthesis layer should be structured so that an LLM can replace or augment the narrative step later.
