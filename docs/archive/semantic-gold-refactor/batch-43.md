# Batch 43

## Goal
Normalize a small set of dirty `Arena.arena_city` labels into cleaner city
names.

## Changes
- `New York` -> `New York City`
- `Mexico City, Mexico` -> `Mexico City`
- `San Juan,Puerto Rico` -> `San Juan`
- `Macao, China` -> `Macau`

## Why
- these values mixed city and country or territory in one field
- one value had formatting noise from a missing space
- `New York City` is more truthful and less ambiguous than `New York`

## Verification
- semantic_gold transform tests cover the four city normalizations
- live Athena/Glue `semantic_gold.arena` should expose the normalized city
  values after rebuild
