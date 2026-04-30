# Value Canonicalization Plan

## Product Goal

The assistant should understand user-facing values like `LAL`, `LA Lakers`,
`Los Angeles Lakers`, `Western Conference`, `west`, and mixed casing without
requiring brittle phrase corridors.

The long-term goal is not to remove lexical matching. The goal is to move
lexical matching to the ontology/value layer, where it is explicit, validated,
and grounded in the semantic contract.

## Current Problem

Value canonicalization currently lives mostly in:

- `services/ontology-hs/src/GroundedPlanning/Resolve/Common/ValueCanonicalization.hs`

That file manually maps a few object/attribute pairs:

- `Team.conference`
- `Team.division`
- `Team.team_name`
- `Team.team_abbreviation`

This works for some important cases, but it is not the right long-term shape.
It makes value understanding hidden planner logic instead of ontology-backed
semantic behavior.

## Design Principle

The schema contract should stay the safety boundary.

If the ontology/data layer can support a value interpretation, the planner
should not reject it because the phrasing was slightly different.

The system should only fail when:

- no matching ontology object/attribute/value exists
- the value match is ambiguous
- the requested predicate/operator is unsupported by the schema contract

## Slice 1: Ontology-Backed Value Aliases

Purpose:

Move current hardcoded value aliases into ontology metadata while preserving
existing behavior.

This slice should add an explicit alias contract to ontology attributes, for
example:

```yaml
attributes:
  - name: conference
    kind: dimension
    source_column: conference
    value_aliases:
      east:
        - east
        - eastern
        - eastern conference
      west:
        - west
        - western
        - western conference
```

Likely files:

- `services/ontology-hs/src/OntologyLayer/Types.hs`
- `services/ontology-hs/src/OntologyLayer/Validation.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Common/ValueCanonicalization.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Common/RowPredicates.hs`
- `services/ontology-hs/src/GroundedPlanning/Resolve/Find.hs`
- `scripts/generate_semantic_ontology.py`
- `pipelines/athena/metadata/semantic_gold_attribute_inventory.json` or a
  deliberate ontology alias overlay if inventory is not the right source

Important note:

`fixtures/ontology/semantic-gold.yaml` is generated. Do not make the canonical
change only in that generated file unless we intentionally accept drift.

Done when:

- Existing team/conference/division canonicalization behavior still works.
- Haskell canonicalization reads alias metadata instead of hardcoded team maps.
- Ontology validation catches duplicate alias collisions within an attribute.
- Tests prove behavior such as `Western`, `eAst`, `LAL`, and `LA Lakers`.

## Slice 2: Data-Backed Value Index

Purpose:

Generate or load canonical values from the actual DuckDB semantic snapshot so
the system can understand real values without manually listing everything.

Examples:

- `team.team_abbreviation = LAL`
- `team.team_name = Lakers`
- `team.team_city = Los Angeles`
- derived user phrase: `Los Angeles Lakers`

Likely approach:

- Build a value index from ontology objects, public dimensions, and DuckDB
  distinct values.
- Use sibling columns on the same object row to generate useful aliases.
- Keep explicit ontology aliases for human nicknames that are not derivable
  from data, such as `Cavs`, `Mavs`, `Sixers`, `Blazers`, and `Wolves`.

Likely files:

- a new Python value-index builder under `apps/cli/` or `scripts/`
- `apps/cli/main.py` or assistant pipeline wiring if the index is created at
  runtime
- Haskell loader/planner wiring if the index is emitted as a static YAML/JSON
  artifact before planning
- tests for value-index generation and end-to-end predicate grounding

Done when:

- Values can be matched from actual semantic data, not only hand-authored
  aliases.
- Ambiguous aliases fail safely instead of guessing.
- The system still preserves the original user wording for assumptions and
  observability.

Implementation note:

- `scripts/generate_semantic_value_aliases.py` builds
  `pipelines/athena/metadata/semantic_gold_value_aliases.yaml` from DuckDB
  snapshot values plus
  `pipelines/athena/metadata/semantic_gold_curated_value_aliases.yaml`.
- `scripts/generate_semantic_ontology.py` then merges that generated alias
  artifact into `fixtures/ontology/semantic-gold.yaml`.
- Haskell remains generic: it only reads `Attribute.value_aliases`.

## Slice 2.5: Curated Ontology Value Aliases

Purpose:

Make human/domain aliases a first-class ontology concept instead of framing
them as implementation overrides.

Some value phrases are not derivable from the current semantic_gold rows. For
example:

- `Cavs` -> `Cavaliers`
- `Mavs` -> `Mavericks`
- `Sixers` -> `76ers`
- `Blazers` -> `Trail Blazers`
- `Wolves` -> `Timberwolves`

These should live in:

- `pipelines/athena/metadata/semantic_gold_curated_value_aliases.yaml`

Done when:

- Generated/data-backed aliases and curated aliases are clearly separated.
- Curated aliases are still merged into the generated ontology contract.
- Product behavior does not change.

## Slice 3: Unify Entity And Predicate Value Resolution

Purpose:

Reduce duplicate matching concepts between comparison entity resolution and
predicate value canonicalization.

Current nearby behavior:

- `apps/assistant/semantic/entity_resolver.py` already resolves comparison entities using the
  ontology and DuckDB.
- Predicate values are canonicalized later in Haskell through
  `ValueCanonicalization.hs`.

Long-term shape:

- One shared value-resolution concept powers comparison entities and predicate
  values.
- The system can explain what it resolved, for example:
  `Interpreted 'LAL' as Lakers.`
- Debug output can show:
  raw user value -> matched canonical value -> object/attribute -> SQL value

Done when:

- Comparison aliases and predicate aliases use the same matching philosophy.
- There is no separate hidden alias map for predicate values.
- Observability makes value-resolution decisions easy to inspect.

## Recommended Order

1. Ontology-Backed Value Aliases
2. Data-Backed Value Index
3. Unified Entity And Predicate Resolution

This order removes the hardcoded Haskell behavior first, then broadens product
coverage, then cleans up duplicated architecture.
