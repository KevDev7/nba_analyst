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
- ontology-grounded display columns carried from the execution plan

For row-style metric/object/aggregate answers, table columns should follow this
general order:

- rank, when the result shape is ranking
- entity columns
- identity metadata, such as team abbreviation
- time metadata, such as season and season type
- filter-context metadata, when a grounded filter is useful to show
- analytical metadata, such as games played or minutes
- evidence metadata, such as the date range behind a recent-game aggregate
- metric/result columns

## Rules

Answer synthesis should:

- stay fully grounded in runtime output
- mention the metric and time window used
- include assumptions when aliases or synonyms were interpreted
- render display columns from execution-plan metadata rather than prompt-specific rules
- avoid inventing any analysis not present in runtime results

## LLM Usage

The live slices do not require a live LLM yet.

The synthesis layer should be structured so that an LLM can replace or augment the narrative step later.
