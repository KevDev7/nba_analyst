# Scope 1 PRD

## Goal

Scope 1 makes the NBA analytics assistant work end to end from the terminal for the five chosen question families.

The core promise is:

```text
one user question
-> one execution plan
-> one answer
```

The system should answer when the ontology and local data snapshot can support the question. If it cannot answer, the failure should come from missing ontology or data depth, not from hardcoded restrictions above the ontology layer.

## Interface

Scope 1 is terminal-only.

The primary interface is:

```bash
python3 apps/cli/main.py "<natural-language question>" --debug
```

Website UI, chatbot memory, generative UI charts, long-lived thread state, and broader sandbox/product shell work are out of scope for Scope 1.

## Question Families

Scope 1 supports these five families:

```text
rank
trend
aggregate
find
compare
```

Each family must work through the same high-level pipeline:

```text
natural-language question
-> semantic draft
-> typed Query IR
-> ontology-grounded validation/resolution
-> execution plan
-> Python runtime result
-> final terminal answer
```

## Layer Ownership

The LLM owns flexible language interpretation.

It should convert messy user language into a semantic draft using user-facing terms. It may capture phrases like "scoring", "pts", "top players", "last ten games", or named entities, but it should not invent SQL, raw table names, raw column names, or final ontology keys.

Haskell owns grounding and validity.

It should map the semantic draft to ontology-backed Query IR, validate that the query is legal, resolve objects/metrics/dimensions/links, and compile an execution plan.

Python runtime owns execution.

It should execute SQL, store intermediate state when a plan has multiple steps, run Python analysis when required, and return structured runtime results.

Answer synthesis owns explanation.

It should turn structured runtime results into a grounded terminal answer. It should explain the result and include assumptions, but it should not invent new analysis beyond what the runtime produced.

## Failure Contract

Scope 1 may fail when:

- the ontology has no matching object, metric, dimension, attribute, or link
- the local data snapshot does not contain the required field/path
- the question is outside the five supported families
- the user question is ambiguous enough that the system cannot safely ground it

Scope 1 should not fail because:

- only one phrase shape was hardcoded
- only one table/object was hardcoded
- only one metric was hardcoded
- limits were restricted to specific values like 1, 5, or 10
- a valid ontology path was blocked without a concrete correctness or safety reason
- a family was captured in the semantic draft but rejected before ontology grounding

Any restriction above the ontology layer must justify:

- what concrete failure it prevents
- why the ontology/schema contract is not enough
- what product flexibility is lost

If that justification is weak, the restriction should be treated as a bug.

## Family Requirements

### Rank

Rank questions ask for top/bottom or leaderboard-style results.

Example:

```text
Show me the top 10 players by points over the last 10 games
```

Expected behavior:

- infer the ranked subject
- infer the metric
- infer the time window
- infer sort direction and limit
- ground subject and metric through the ontology
- return a ranked terminal table

### Trend

Trend questions ask for a metric over time.

Example:

```text
Show me monthly points by team over the past year
```

Expected behavior:

- infer the metric
- infer the time grain
- infer the time window
- optionally infer a series/grouping dimension
- ground the time bucket through ontology-supported derived attributes or data fields
- return a time-series terminal table

### Aggregate

Aggregate questions ask for summary calculations grouped by one or more business dimensions.

Example:

```text
Calculate average points by team over the last 10 games
```

Expected behavior:

- infer the aggregate metric
- infer the grouping dimension
- infer the time window or filter context
- ground the metric and grouping through the ontology
- return a grouped summary terminal table

### Find

Find questions ask for rows or entities matching filters.

Example:

```text
Find games where the Lakers scored over 120 points
```

Expected behavior:

- infer the target object
- infer filters
- resolve linked entities through ontology paths when needed
- return matching rows or entities in the terminal

### Compare

Compare questions ask for a comparison between named entities.

Example:

```text
Compare Brunson and Haliburton scoring over the last 10 games
```

Expected behavior:

- infer the compared entities
- infer the comparison metric
- infer the time window
- ground entities and metric through the ontology/data
- produce one execution plan and one final comparison answer

The execution plan may contain multiple internal steps, such as SQL followed by Python analysis, as long as the user interaction remains one question to one answer.

## Acceptance Tests

Scope 1 is complete when each family has at least one terminal-level end-to-end test:

```text
rank:
Show me the top 10 players by points over the last 10 games

trend:
Show me monthly points by team over the past year

aggregate:
Calculate average points by team over the last 10 games

find:
Find games where the Lakers scored over 120 points

compare:
Compare Brunson and Haliburton scoring over the last 10 games
```

Each acceptance test should prove:

- natural language reaches the semantic draft layer
- semantic draft becomes typed Query IR
- Haskell validates, resolves, and compiles an execution plan
- Python runtime executes the plan
- answer synthesis returns a terminal-readable response

Scope 1 should also include negative tests proving unsupported questions fail for ontology/data reasons instead of avoidable hardcoded restrictions.

## Non-Goals

Scope 1 does not include:

- website or chat UI
- chatbot memory inside a thread
- generative UI charts
- production Python sandboxing
- broad connector support
- large-scale infrastructure concerns
- polished dashboard or artifact UX

Those can build on Scope 1 after the terminal-first semantic pipeline is trustworthy.

