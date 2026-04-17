# Deferred Semantic And Copilot Gaps

This file tracks meaningful remaining gaps after the current deterministic chat surface. It is the current deferred-gap register for the warehouse and application layers.

Review note:
- reviewed against the current live Athena gold surface on March 29, 2026
- this file is intentionally directional rather than a schema inventory, so the warehouse metadata and deploy scripts remain the source of truth for current implemented fields and views

## Current shipped foundation

The app already supports:

- threaded chat sessions
- contextual follow-ups over bounded thread state
- rankings, comparisons, game logs, split comparisons, and trends
- playoff support
- date-range support
- clarification for ambiguous player names
- warehouse freshness metadata

## Deferred gaps

### 1. Ontology and richer semantic abstraction

The current semantic contract is strong enough for deterministic asks, but it is not yet a full ontology.

Still missing:

- richer entity semantics beyond current player/team/game/season coverage
- explicit relationship metadata for broader routed reasoning
- curated role/archetype metadata for evaluative and hypothetical analysis
- stronger metric-family metadata for broader open-ended planning

### 2. Open-ended evidence planning

The current app handles bounded deterministic questions and natural contextual follow-ups, but it does not yet decompose broad asks into multi-query evidence plans.

Still missing:

- routed open-ended ask classification
- structured evidence-plan generation
- multi-query orchestration for one user question
- answer synthesis over an evidence bundle instead of one query result

### 3. Compute layer for deeper analysis

Some future questions will need more than direct SQL retrieval.

Examples:

- player-vs-player evaluative arguments
- hypothetical lineup evaluation
- deeper fit / style / tradeoff analysis

Still missing:

- controlled compute layer for post-SQL analysis
- explicit separation between evidence-backed observations and projected reasoning

### 4. Advanced basketball semantics

Not modeled strongly enough yet:

- offensive / defensive / net rating
- pace and possession-derived metrics
- lineup and on/off analytics
- clutch and play-type splits
- shot-location / tracking data

Why deferred:
- these need clearer lineage, broader source coverage, and stronger gold definitions before the app can expose them safely

### 5. Retrieval and knowledge grounding

The app does not yet retrieve grounded context from:

- ontology / metric docs
- approved question -> plan -> SQL examples
- instructions / business rules

This is the next major step toward broader but still trustworthy coverage.

### 6. Richer trust and evidence provenance

Current provenance already includes:

- contract version
- metric label
- tables used
- Athena query id
- row count
- duration
- freshness date surfaced in the UI

Still missing:

- bytes scanned / cost signals
- source-file / partition lineage
- evidence-bundle provenance for multi-query answers
- stronger warehouse quality flags for downstream answer synthesis

### 7. First-class charts and knowledge writeback

Current trend outputs are chart-ready, but chart rendering and learning loops are still deferred.

Still missing:

- first-class charts in the UI
- chart config persistence where needed
- thumbs up/down and approved-example writeback
- retrieval/eval growth from real production usage
