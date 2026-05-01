# Deferred Semantic And Copilot Gaps

This file tracks meaningful remaining gaps after the current deterministic chat surface. It is the current deferred-gap register for the warehouse and application layers.

Review note:
- reviewed against the current live semantic assistant surface on April 30, 2026
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
- ontology-backed `Player`, `Team`, `Arena`, `Game`, `PlayerGame`,
  `TeamGame`, `PlayerSeason`, `PlayerSeasonTeam`, and `TeamSeason` objects
- expanded TeamGame and TeamSeason boxscore metric coverage for team-grain
  scoring, assists, rebounds, steals, blocks, fouls, turnovers, shooting
  makes/attempts, and opponent mirrors where the local semantic snapshot has
  populated signal

## Deferred gaps

### 1. Ontology and richer semantic abstraction

The current semantic contract now has a real ontology-backed object and metric
surface for the supported one-step assistant path, but it is not yet a full
domain ontology for broad routed reasoning.

Still missing:

- richer entity semantics beyond the current basketball stat objects
- broader relationship metadata for routed reasoning outside the current graph
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

The semantic layer now exposes broad team boxscore totals and averages where the
snapshot has populated signal. The remaining gap is stronger advanced-basketball
meaning and lineage, not basic team assists/rebounds/boxscore coverage.

Still not modeled strongly enough:

- metric-family metadata that explains rate, percentage, possession, and
  efficiency concepts to planning and answer synthesis
- audited TeamGame rate/percentage/pace/ratio metric exposure; fields such as
  `pace`, `field_goals_percentage`, `true_shooting_percentage`, and
  `assist_to_turnover_ratio` are populated but intentionally deferred from
  ontology metric exposure until scale/formula semantics are verified
- lineup and on/off analytics
- clutch and play-type splits
- shot-location / tracking data

Why deferred:
- these need clearer lineage, broader source coverage, stronger gold
  definitions, or explicit semantic metadata before the app can expose them
  safely

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
