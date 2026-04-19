# Athena Databricks Alignment History

> **Status:** Historical record. This document explains how the Athena pipeline
> was aligned to the Databricks-designed supported warehouse contract. It is not
> the current execution plan or the primary source of truth for the live
> product. Athena remains the active warehouse/runtime path in this repo. For
> current behavior, prefer the repo README, the active Athena transform/deploy
> scripts, and the Athena metadata docs.

## Historical Purpose

Refactor the Athena pipeline so its supported warehouse contract matches the
current Databricks pipeline design as closely as possible, without introducing
Spark or Delta-specific runtime assumptions.

This is not a file-by-file port.

The goal is:

- keep Athena on `S3 + parquet + Athena`
- adopt the Databricks table contracts, module boundaries, and supported output surface
- avoid preserving Athena-only complexity that Databricks intentionally deferred

Historical reference documents:

- The original Databricks-side contract files referenced during this migration
  are no longer kept in this repo.
- Treat this note as narrative history, not as an executable parity checklist.

Recorded outcome:

- This migration is complete through the Databricks-supported surface.
- Athena now matches Databricks across silver, gold tables, and the supported gold views.
- The old Athena-only possession/on-court gold branch was removed after Phase 5.

## Core Read

After scanning both pipeline trees:

- Silver is already structurally close across Athena and Databricks.
- Gold is not a direct parity port. Databricks simplified the supported gold
  surface and explicitly deferred some possession/on-court advanced metrics.
- Because of that, the right migration strategy is contract-first:
  - align silver first
  - align gold core second
  - treat deferred Athena-only gold logic as optional follow-up work, not phase 1 scope

## Principles

1. Keep raw ingestion unchanged.
2. Keep event grain, possession grain, and lineup grain as separate tables.
3. Prefer Databricks-supported contracts over legacy Athena behavior when they conflict.
4. Do not migrate the full Athena gold surface until the Databricks-supported gold core is stable.
5. Replace runner-centric script behavior with clearer module boundaries and smaller validation targets.

## Target Surface

### Must Match

- silver play-by-play event contract
- silver possessions
- silver on-court state
- silver reference tables already shared by both systems
- gold core dimensions and facts
- gold supported season/rate views currently backed by Databricks

### Defer

- Athena-only player possession denominator path
- Athena-only on-court context cache
- Athena-only advanced player-season views that Databricks explicitly deferred

## Historical Vertical Slices

### 1. Silver Contract Parity

Priority: highest

Cluster:

- `build_silver_playbyplay_events.py`
- `build_silver_possessions.py`
- `build_silver_on_court_state.py`
- silver metadata helpers

Why first:

- These tables define the semantic foundation for every downstream gold model.
- The Databricks play-by-play contract is more explicit and should become the Athena target.

Dependency category:

- local-substitutable

Main deliverables:

- Align Athena `silver/playbyplay` columns to the Databricks contract in
  the historical event-contract shape described in this note
- Ensure possession and on-court outputs use the same semantic assumptions as the Databricks versions
- Reduce source-shaped special cases that are no longer part of the intended contract

Acceptance signal:

- Event-grain tables validate at the same contract boundary as Databricks
- Possessions and on-court state pass game-level parity checks on a shared validation set

### 2. Silver Orchestration Cleanup

Priority: high

Cluster:

- `transform/silver/run_silver_pipeline.py`
- `transform/silver/silver_pipeline_helpers.py`
- state, audit, reconciliation, and verification scripts

Why second:

- Athena still carries script-first orchestration and state-file behavior that makes changes riskier than they need to be.
- The silver modules should be easier to run independently and validate at a table boundary.

Dependency category:

- true external

Main deliverables:

- Separate transform logic from orchestration concerns
- Make processed-game selection, state tracking, and audit writing explicit interfaces
- Shrink reliance on broad runner behavior for confidence

Acceptance signal:

- A single silver table can be rebuilt and validated independently
- Audit/state behavior is testable without depending on the full orchestrator

### 3. PBPStats Sidecars

Priority: medium-high

Cluster:

- `pbpstats` event projection
- `pbpstats` event-context sidecar

Why third:

- Databricks added new semantic sidecars that are part of the intended warehouse direction.
- Athena already has the planning material, but not the same concrete architecture.

Dependency category:

- local-substitutable

Main deliverables:

- Add Athena equivalents of:
  - `build_silver_pbpstats_event_projection_v1.py`
  - `build_silver_pbpstats_event_context_v1.py`
- Keep them as separate silver tables rather than stuffing more columns into the main event table

Acceptance signal:

- Sidecars exist at their own grain
- Event, lineup, and possession semantics remain separated cleanly

### 4. Gold Core Alignment

Priority: medium-high

Cluster:

- `dim_date`
- `dim_game`
- `dim_player`
- `dim_team`
- `fct_player_game`
- `fct_team_game`
- `agg_player_season`
- `agg_team_season`

Why fourth:

- This is where the two pipelines diverge most in shape and complexity.
- Databricks gold should be treated as the supported target surface, not as a direct port of all Athena logic.

Dependency category:

- in-process

Main deliverables:

- Refactor Athena gold modules to mirror the Databricks-supported table contracts
- Simplify Athena gold where Databricks intentionally simplified it
- Preserve SCD2 and fact-building behavior only where it is still part of the supported target

Acceptance signal:

- Athena gold can answer the same minimum supported question set described in
  this historical alignment note

### 5. Supported View Surface

Priority: medium

Cluster:

- season rate views
- PIE view
- rebound percentage view
- team advanced view

Why fifth:

- View parity is only meaningful after the underlying gold tables match the intended Databricks-supported surface.
- Athena currently carries a broader set of views than Databricks supports.

Dependency category:

- in-process

Main deliverables:

- Align Athena view SQL to the Databricks-supported subset
- Move unsupported or deferred views out of the phase 1 target

Acceptance signal:

- Supported Athena views produce the same semantic answers as the Databricks-backed question suite

### 6. Deferred Athena-Only Gold

Priority: last

Cluster:

- legacy Athena-only possession/on-court gold branch
- advanced player-season possession/on-court views

Why last:

- Databricks explicitly deferred this family.
- Keeping it in scope from the start would blur whether we are aligning to Databricks or preserving old Athena behavior.

Dependency category:

- in-process

Main deliverables:

- Decide whether these modules still belong in the supported Athena surface
- If yes, rebuild them on top of the new silver contract instead of preserving them unchanged
- If no, remove them from the active Athena codebase

Acceptance signal:

- This layer is either intentionally removed from the supported surface or rebuilt on top of the aligned silver/gold contracts

Status update:

- The Athena-only possession/on-court gold branch was removed after Phase 5.
- Athena now fully commits to the Databricks-aligned supported surface.

## Historical Execution Order

1. Silver contract parity
2. Silver orchestration cleanup
3. PBPStats sidecars
4. Gold core alignment
5. Supported views
6. Deferred Athena-only gold decision

## Historical Validation Matrix

Phase 0 exists to lock the comparison method before refactoring Athena code.

The purpose is to prevent later ambiguity about whether a mismatch came from:

- source coverage differences
- silver semantic drift
- possession/on-court logic drift
- gold aggregation drift
- view/query drift

### Validation Environments

- Athena side:
  - S3 parquet outputs
  - Athena SQL / AWS MCP checks
- Databricks side:
  - Databricks SQL / Databricks MCP checks
- Local side:
  - repo unit tests
  - targeted game-level transform checks

### Validation Modes

Use three levels of validation.

1. Contract checks
- schema
- grain uniqueness
- required-column coverage
- nullability expectations where applicable

2. Table-result parity checks
- row counts
- `COUNT(DISTINCT primary_key)`
- game coverage
- season coverage
- sampled row-level parity on fixed keys

3. Business-answer parity checks
- identical prompts/questions run against Athena and Databricks
- compare final metric outputs, not just intermediate tables

### Fixed Validation Sets

Use fixed datasets for every phase so regressions are comparable over time.

#### Silver Validation Games

Keep a shared validation game set covering:

- regular season
- playoffs
- play-in
- close games
- overtime games
- substitution-heavy games
- foul/free-throw edge-case games
- possession-boundary edge cases

Candidate sources already in repo:

- [`metadata/playbyplay_enrichment_validation_games.csv`](metadata/playbyplay_enrichment_validation_games.csv)
- [`metadata/playbyplay_phase_1_3_expanded_validation_games.csv`](metadata/playbyplay_phase_1_3_expanded_validation_games.csv)
- [`metadata/playbyplay_phase0_validation_games.csv`](metadata/playbyplay_phase0_validation_games.csv)

Current Phase 0 execution rule:

- Use [`metadata/playbyplay_phase0_validation_games.csv`](metadata/playbyplay_phase0_validation_games.csv)
  as the fixed warehouse-parity subset for silver `playbyplay`.
- Use the remaining phase validation scripts for baseline row-count, grain, and
  action-shape checks.
- Because the live Athena catalog does not currently register `silver/playbyplay`
  as an external table, the Athena-side comparison should read the S3 parquet
  objects directly until silver table registration exists.

#### Gold Validation Seasons

Keep a small fixed season set:

- `2024-25 regular season`
- `2024-25 playoffs`
- `2025-26 regular season` when coverage is sufficient

### Phase 0 Deliverables

#### 0.1 Table Inventory

Define the tables that are in-scope for parity by phase.

Phase 1:

- `silver/playbyplay`

Phase 2:

- `silver/possessions`
- `silver/on_court_state`

Phase 3:

- `silver/pbpstats_event_projection_v1`
- `silver/pbpstats_event_context_v1`

Phase 4:

- `legacy_gold/dim_date`
- `legacy_gold/dim_game`
- `legacy_gold/dim_player`
- `legacy_gold/dim_team`
- `legacy_gold/fct_player_game`
- `legacy_gold/fct_team_game`
- `legacy_gold/agg_player_season`
- `legacy_gold/agg_team_season`

Phase 5:

- supported Athena/Databricks gold views

#### 0.2 Parity Queries

For every in-scope table, define a minimum query set.

Minimum contract query set:

- row count
- primary-key distinct count
- duplicate-key detection
- min/max season coverage
- min/max game-date coverage where relevant

Minimum sampled parity query set:

- fixed `game_id` sample row counts
- fixed `season_year` sample counts
- targeted event/action counts by type
- targeted possession/stint counts by game

#### 0.3 Question Suite

Use the Databricks gold question suite as the default supported business surface:

- use the historical supported question set summarized in this note

Athena is considered aligned only if it can answer the same supported questions
with materially matching results.

### Acceptance Gates By Phase

#### Phase 1 Gate: `silver/playbyplay`

Required:

- schema contract matches intended event-table contract
- no duplicate `(gameId, actionNumber)`
- selected validation games match Databricks on:
  - row count
  - action type distribution
  - key semantic flags
  - score progression sanity

#### Phase 2 Gate: `silver/possessions` and `silver/on_court_state`

Required:

- no duplicate possession/stint primary keys
- selected validation games match Databricks on:
  - possession counts
  - lineup/stint counts
  - start/end boundaries

#### Phase 3 Gate: `pbpstats` sidecars

Required:

- sidecar grain is correct
- sidecars join cleanly back to the canonical event table
- sampled games match Databricks on projected/event-context outputs

#### Phase 4 Gate: gold core

Required:

- dim/fact grains are unique
- aggregate row counts match Databricks for supported seasons
- sampled player/team outputs are materially aligned

#### Phase 5 Gate: supported views

Required:

- the supported business question suite returns materially matching answers on Athena and Databricks

### Comparison Strategy

Do not compare everything at once.

Compare in this order:

1. schema and grain
2. row counts and coverage
3. sampled row-level parity
4. derived metric parity
5. end-user question parity

This keeps failures localized. If `silver/playbyplay` drifts, the error should
be caught before any gold comparison starts.

### Pass / Fail Rules

Contract failures are hard failures:

- missing required columns
- wrong grain
- duplicate primary keys
- broken season/game coverage

Metric mismatches should be classified:

- expected unsupported difference
- tolerable numeric drift
- true logic regression

Unsupported Athena-only outputs should not block alignment unless they are still
explicitly in the supported target surface.

## Historical First Phase

The best first implementation phase is:

1. Treat `silver/playbyplay`, `silver/possessions`, and `silver/on_court_state`
   as one refactor program.
2. Define the Athena-side contract target from the Databricks docs first.
3. Update tests to validate the contract boundary rather than the old runner behavior.
4. Only after silver is stable, begin gold-core refactors.

This keeps the rewrite narrow and reduces the risk of mixing semantic changes
with gold-aggregation changes in the same step.

## What Should Not Happen

- Do not port all Athena gold views before silver semantics are settled.
- Do not preserve every Athena-only advanced metric just because it exists.
- Do not couple the refactor plan to Spark-specific Databricks mechanics.
- Do not treat runner scripts as the core architecture.

## Success Criteria

- Athena silver matches the intended Databricks event/possession/lineup contracts.
- Athena gold supports the same core question surface Databricks currently supports.
- Unsupported advanced player-season possession/on-court outputs are explicitly deferred or rebuilt, not left ambiguous.
- Athena remains operational on `S3 + parquet + Athena` without Spark-specific assumptions.

## Historical Next Step

At the time this document was written, the next intended move was to turn Slice
1 into a concrete implementation plan:

- exact Athena files to modify
- target contract changes per table
- tests to keep, replace, or delete
- validation games and acceptance gates for each silver table

That step is retained here only as historical context. It should not be read as
the current repo priority or as an active to-do list.
