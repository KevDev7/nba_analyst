# Event Stack Architecture

Status: current contract map for the remaining event-stack refactor slices.
Last reviewed: 2026-05-11.

This note is intentionally operational. It documents how the current silver event
stack is wired today, what downstream contracts must remain stable, and where
future module splits should land. The supported script entrypoints stay stable
unless a later slice explicitly replaces them and updates the runner/runbooks.

## Current Dependency Graph

Raw and bronze inputs:

- CDN play-by-play payloads
- CDN boxscore payloads
- NBA Stats schedule and boxscore-family payloads
- vendored `pbpstats` reference code for pbpstats-derived projections/context

Silver flow:

1. `build_silver_playbyplay_events.py` builds `silver/playbyplay/`.
2. `build_silver_event_projection_v2.py` builds `silver/event_projection_v2/`.
3. `build_silver_pbpstats_event_projection_v1.py` builds
   `silver/pbpstats_event_projection_v1/`.
4. `build_silver_pbpstats_event_context_v1.py` builds
   `silver/pbpstats_event_context_v1/`.
5. `build_silver_on_court_state.py` builds `silver/on_court_state/`.
6. `build_silver_possessions.py` builds `silver/possessions/`.
7. `build_silver_possessions_ot_fallback.py` builds
   `silver/possessions_ot_fallback/`.
8. Player/team possession, opportunity, and defensive-shot context tables consume
   the event, on-court, possession, and boxscore-family outputs.

Gold and serving tables should not see schema changes from the refactor. The
goal is a clearer silver implementation path, not a new serving contract.

## Current Entrypoints

| Entrypoint | Main output | Current responsibility |
| --- | --- | --- |
| `build_silver_playbyplay_events.py` | `silver/playbyplay/` | Raw event normalization, boxscore context, period/score/clock/state enrichment, audit/checkpoint orchestration. |
| `build_silver_event_projection_v2.py` | `silver/event_projection_v2/` | Raw-first event projection with duplicate-action handling, neighbor links, penalty hints, and lightweight game-state context. |
| `build_silver_pbpstats_event_projection_v1.py` | `silver/pbpstats_event_projection_v1/` | PBPStats-backed event projection using the vendored `pbpstats` loader/common helpers. |
| `build_silver_pbpstats_event_context_v1.py` | `silver/pbpstats_event_context_v1/` | PBPStats event context plus boxscore orientation and raw play-by-play joins. |
| `build_silver_on_court_state.py` | `silver/on_court_state/` | Starter inference, substitutions, stints, and per-event on-court player state. |
| `build_silver_possessions.py` | `silver/possessions/` | Exact possession materialization with pbpstats alignment, source stamping, checkpoint/audit orchestration. |
| `build_silver_possessions_ot_fallback.py` | `silver/possessions_ot_fallback/` | Overtime fallback possession families for unresolved/excluded games. |
| context build scripts | context-specific silver tables | Player/team possession, opportunity, and defensive-shot context derivations. |

## Contracts To Preserve

- Bronze/raw inputs remain source-faithful. Refactors must not rewrite raw payload
  semantics to make silver easier.
- Silver outputs remain parquet in the same S3 prefixes and local table names.
- `game_id` remains the stable per-game join and partition key. Normalize it as a
  zero-padded 10-character id before writing silver rows.
- Event identity stays source-specific:
  - raw/CDN event tables use `action_number` where that is the source event key
  - pbpstats-derived tables use pbpstats event identifiers such as `event_num`
  - possession outputs use their possession identifiers and must retain source
    stamping fields used by downstream context tables
- Incremental heavy-table behavior remains checkpoint-first through shared
  runtime state. Legacy JSON state is rollback compatibility, not the primary
  mechanism.
- Audit and detail artifacts must continue to expose selected games, written
  games, skipped games, errors, warnings, checkpoint usage, and target-game
  metadata.
- Boxscore fallbacks used by context tables must stay explicit. If a fallback is
  an estimate, the output should preserve enough source/fallback metadata for QA.
- Refactors must keep script entrypoints usable for targeted backfills and the
  silver runner.

## Target Module Boundaries

Recommended future package layout under `pipelines/athena/transform/silver/`:

- `playbyplay/`
  - `contracts.py`: row keys, required columns, event id normalization
  - `sources.py`: raw CDN play-by-play loading and target-game discovery
  - `boxscore_context.py`: boxscore context fetch/build helpers
  - `normalization.py`: source event flattening and base row normalization
  - `phase1.py`, `phase2.py`, `phase3.py`, `phase6.py`: existing enrichment
    phases split by current behavior
  - `pipeline.py`: per-game orchestration used by the stable build script
- `event_projection/`
  - raw-first projection v2 transforms, duplicate-action handling, neighbor links,
    and projection-specific validation
- `pbpstats_events/`
  - vendored pbpstats path resolution, loader setup, projection building, context
    building, and pbpstats-specific validation
- `on_court/`
  - starter inference, substitution processing, stint construction, per-event
    state expansion, and validation
- `possessions/`
  - keep the existing package as the possession domain home
  - move only script-level source discovery, checkpointing, and S3/audit shell
    logic out of the build scripts when it materially improves readability
- `game_context/`
  - shared input loading, player/team possession context helpers, opportunity
    context helpers, defensive-shot context helpers, and fallback estimators

Each stable `build_silver_*.py` file should become a thin executable wrapper over
one package-level `main` or `run` function after its slice is complete.

## Refactor Order

1. Fix or clearly isolate shared path/config issues before relying on broader
   pbpstats validations.
2. Split play-by-play source loading, boxscore context, and enrichment phases.
3. Split raw-first event projection v2.
4. Split pbpstats projection/context around one shared pbpstats loader/config
   module.
5. Split on-court state into starters, substitutions, stints, state expansion,
   and validation.
6. Tighten possessions and OT fallback wrappers around the existing possession
   package.
7. Split player/team possession, opportunity, and defensive-shot context into
   shared game-context modules.

## Verification Matrix

- Focused unit tests for every changed build script and new package module.
- Contract tests that compare row counts, required columns, grain, and key nulls
  for changed silver outputs.
- Existing parity scripts for play-by-play phases, event projections, pbpstats
  context, and possession behavior when a slice touches those domains.
- Quality-layer grain, schema drift, source completeness, and silver-to-gold
  reconciliation after the quality runner owns those checks.
- Targeted S3/backfill spot checks for any slice that changes source discovery,
  incremental selection, or write paths.

## Known Risks

- Several pbpstats paths still refer to `reference/pbpstats` while the current
  repository layout uses `references/`. Correctness triage should resolve this
  before treating pbpstats live validations as healthy.
- The event stack has both raw-first and pbpstats-derived event models. Do not
  collapse them into one abstraction unless the output contracts remain explicit.
- Context builders currently share helpers by importing from
  `build_silver_player_game_possession_context.py`. Later slices should move
  shared logic into a neutral package before deleting those imports.
- Serving snapshot parity currently has a separate configured path issue. It is
  outside this event-stack slice but remains part of the final refactor plan.

## Non-Goals For The Refactor

- No gold table schema changes.
- No serving/semantic table contract changes.
- No new gold exposure for event-stack internals.
- No mutation of bronze/raw source files.
- No replacement of pbpstats-derived logic with hand-rolled approximations unless
  a later correctness pass proves the replacement is equivalent or better.
