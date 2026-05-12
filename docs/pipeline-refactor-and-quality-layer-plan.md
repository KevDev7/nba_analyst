# Pipeline Refactor And Quality Layer Plan

Status: big-picture planning draft.

This document is a north-star plan for making the data pipeline easier to understand, safer to refactor, and more navigable for humans and agents. It is intentionally not a rigid implementation contract. During implementation, new facts may require changing the order, slice boundaries, or exact design.

The goal is to improve the pipeline that produces the existing gold and serving surfaces without changing those public outputs.

## Guiding Principles

- Keep gold and serving table names, schemas, and business meaning stable unless a separate product decision says otherwise.
- Preserve raw/bronze source faithfulness. Raw and bronze should not become interpretation layers.
- Make silver easier to navigate first, because most transformation complexity lives there.
- Use quality outputs as guardrails before moving major logic.
- Do not leave long-term duplicate paths behind. Refactor slices should include deletion or an explicit supported-fallback decision.
- Prefer deeper domain modules with small entrypoints over large scripts where orchestration, parsing, validation, and S3 IO are all mixed together.

## Desired End State

The pipeline should remain conceptually:

```text
raw / bronze -> silver -> legacy_gold -> semantic_gold / serving
```

Add a sidecar quality area:

```text
quality/
```

The quality layer observes the pipeline. It should not become a business-facing data layer.

Example S3 shape:

```text
s3://nba-analytics-lakehouse-dev/quality/
  pipeline_runs/
  table_profiles/
  schema_snapshots/
  grain_checks/
  reconciliation/
  source_completeness/
  quarantine_summaries/
```

## Proposed Slice Order

### Slice 1: Pipeline Registry

Create a single source of truth for pipeline table metadata.

Minimum useful fields:

- `layer`
- `table_name`
- `grain`
- `source_keys`
- `destination_key`
- `entrypoint`
- `dependencies`
- `is_heavy`
- `checkpoint_key`
- `schema_owner`
- `gold_or_serving_exposure`

Purpose:

- Give humans and agents a map before refactoring.
- Make table dependencies visible.
- Reduce the need to infer pipeline order from script names.

Cleanup gate:

- No deletion required yet.
- Existing docs that conflict with the registry should be marked stale or updated once the registry is trusted.

### Slice 2: Thin Quality Layer And Baseline

Create the initial `quality/` layer with only the checks needed to protect refactors.

Initial outputs:

- table row counts
- schema snapshots
- grain duplicate checks
- key-column null/profile summaries
- reconciliation summaries
- latest run status by table
- quarantine summaries where applicable

Purpose:

- Capture the current behavior before refactoring.
- Give each later slice a before/after comparison point.

Cleanup gate:

- No major old logic deletion yet.
- Any existing audit output that remains authoritative should either be linked from `quality/` or documented as intentionally separate.

### Slice 3: Silver Easy Domains Refactor And Delete

Refactor lower-risk silver domains into deeper domain modules while keeping current script entrypoints working.

Candidate domains:

- boxscore
- schedule
- player movement
- shot location
- matchups

Expected shape:

```text
pipelines/athena/transform/silver/<domain>/
  contracts.py
  sources.py
  transform.py
  quality.py
  pipeline.py
```

The exact files can vary by domain. The important part is that the build script becomes a thin entrypoint, while domain logic moves into testable modules.

Cleanup gate:

- Delete duplicated helper functions that the new domain module replaces.
- Delete stale one-off scripts if they are no longer a supported path.
- Update or remove old docs that describe the previous flow.
- A slice is not complete if both old and new logic remain active without a documented reason.

### Slice 4: Silver Hard Domains Refactor And Delete

Refactor the high-complexity silver areas only after the quality baseline is useful.

Candidate domains:

- play-by-play events
- event projections
- on-court state
- possessions
- player-game context
- team-game context
- opportunity and defensive shot context

Purpose:

- Make event and possession logic easier to reason about.
- Reduce script-level sprawl.
- Make validation possible at domain boundaries instead of only through full backfills.

Cleanup gate:

- Delete obsolete event/possession helper paths after parity checks pass.
- Remove deprecated env vars or document them as supported.
- Remove old planning notes that no longer match implementation reality.
- Keep only one supported runtime path per table unless a fallback is explicitly intentional.

### Slice 5: Gold Internal Refactor And Delete

Keep all gold outputs stable, but simplify the implementation.

Targets:

- shared table specs
- shared S3 read/write helpers
- shared DDL helpers
- shared schema registration patterns
- clearer gold dependency ordering

Purpose:

- Reduce repeated boilerplate across gold transforms.
- Make it easier to see how each gold table is built.
- Keep serving and semantic gold contracts stable.

Cleanup gate:

- Delete duplicate DDL/schema/S3 helper code after shared helpers are adopted.
- Remove obsolete gold scripts or wrappers that no longer serve a supported table.
- Run quality comparisons against the pre-refactor baseline before calling the slice done.

### Slice 6: Bronze / Raw Cleanup And Delete

Clean ingestion lightly. Do not change source-faithful raw behavior unless required for correctness.

Targets:

- endpoint/source manifests
- common fetch/session/write helpers
- source key conventions
- backfill manifest conventions
- retry/rate-limit behavior

Purpose:

- Make it clear which raw source owns each downstream table.
- Reduce one-off ingestion scripts where possible.
- Keep raw and bronze folders easy to audit.

Cleanup gate:

- Delete abandoned probes, stale endpoint experiments, and old fallback scripts that are no longer supported.
- If a fallback remains, document its source, output prefix, and when to use it.
- Do not delete reference clones or raw archives unless they are clearly out of scope and confirmed unnecessary.

### Slice 7: Quality Expansion And Final Prune

After the refactor stabilizes, expand `quality/` beyond the thin baseline.

Candidate additions:

- source completeness by season and source family
- silver-to-gold parity checks
- schema drift history
- row-count trend history
- anomaly summaries
- quarantine trend summaries
- source-vs-derived mismatch summaries
- serving snapshot quality summaries

Purpose:

- Turn quality from refactor guardrail into ongoing pipeline observability.
- Make future backfills and agent-driven changes safer.

Cleanup gate:

- Repo-wide stale-code and stale-doc pass.
- Remove old parity plans that are only narrative history, or move them under an archive area.
- Remove duplicate quality scripts once their results are represented in `quality/`.

## Deletion Rule

No refactor slice is complete until old logic is either:

1. deleted, or
2. explicitly documented as a supported fallback with when/why/how to use it.

This is important because long-term scaffolding makes the pipeline harder to understand than the original mess.

## Recommended Overall Order

```text
1. registry
2. thin quality baseline
3. silver easy domains refactor + delete
4. silver hard domains refactor + delete
5. gold internal refactor + delete
6. bronze cleanup + delete
7. quality expansion + final prune
```

## What Should Not Change Without A Separate Decision

- Existing gold table names.
- Existing serving and semantic-gold contracts.
- Raw/bronze source-preservation rules.
- S3 source prefixes for existing raw data.
- Business definitions of existing metrics.

## How To Use This Plan

Every slice should follow the same two-pass rhythm:

1. **Research pass**: inspect the relevant code and docs using the `research-pass` workflow. Do not edit behavior during this pass. End with the current facts, recommended implementation boundary, files likely to change, blockers, and verification plan.
2. **Implementation pass**: implement the slice, verify it, and complete the cleanup gate.

After each slice, pause long enough to decide whether reality discovered during the work requires an inserted slice before continuing. Inserted slices should be numbered between existing slices, such as `2.5`, and should follow the same research-pass then implementation-pass rhythm.

Before implementing each slice:

1. Re-read the current code and docs.
2. Confirm the slice still makes sense.
3. Identify the smallest useful boundary.
4. Define the quality checks that prove behavior stayed stable.
5. Implement the refactor.
6. Delete stale logic or document the fallback.
7. Update this plan if reality changed.

## Follow-Up: Aggressive Cleanup Plan

Status: planned follow-up after the initial seven-slice navigation/refactor pass.

The first seven-slice pass should make the pipeline easier to navigate and create
guardrails. This follow-up is the more aggressive deletion pass. Its goal is to
remove old scaffolding and stale paths only after we have stronger evidence that
gold and serving outputs remain stable.

Use the same pattern as above for every slice:

1. **Research pass** using the `research-pass` workflow.
2. **Implementation pass**.
3. Verification.
4. Delete stale logic or document the remaining supported fallback.
5. Decide whether an inserted in-between slice is needed.
6. Continue to the next slice unless there is a real blocker or product decision.

### Aggressive Slice 1: Real Quality Baseline

Run the new quality manifest against current S3/Athena outputs and persist the
first real `quality/` artifacts.

Purpose:

- Capture current row counts, schemas, grain checks, source completeness,
  quarantine summaries, and anomaly summaries before deeper deletion.
- Make later cleanup evidence-based instead of intuition-based.

Cleanup gate:

- Any existing audit output that remains authoritative should be linked from the
  quality baseline or documented as intentionally separate.
- Do not delete transform logic in this slice unless it is clearly unused by the
  baseline and already unsupported.

### Aggressive Slice 2: Gold Parity Lock

Add and run row-count, schema, grain, and parity checks for all current gold and
serving tables.

Purpose:

- Prove existing gold and serving outputs stay stable before deleting deeper
  pipeline paths.
- Create the acceptance test for later cleanup slices.

Cleanup gate:

- Remove or archive stale gold parity notes that conflict with the new parity
  checks.
- Keep any older parity runner only if it covers a backend or scenario the new
  checks do not cover, and document that reason.

### Aggressive Slice 3: Silver Domain Deletion Pass

Remove duplicated helper logic and unsupported stale paths in silver where the
registry, silver pipeline plan, quality layer, and shared heavy runtime already
define the supported path.

Purpose:

- Reduce silver script sprawl.
- Keep one supported runtime path per silver table unless a fallback is
  explicitly intentional.

Cleanup gate:

- Delete duplicated helpers replaced by shared modules.
- Delete old one-off silver scripts that are no longer a supported path.
- Document any remaining fallback with when, why, and how to use it.

### Aggressive Slice 4: Gold Deploy And Transform Cleanup

Clean gold internals more aggressively while preserving all public gold and
serving tables.

Purpose:

- Remove duplicate deploy wrappers, stale view deploy paths, old spec
  definitions, and outdated docs after parity passes.
- Keep gold implementation easier to reason about without changing business
  definitions.

Cleanup gate:

- Delete obsolete deploy wrappers and duplicate table/view spec definitions.
- Remove old docs/plans that describe paths no longer present.
- Re-run the gold parity lock before calling the slice done.

### Aggressive Slice 5: Raw/Bronze And Repo-Wide Final Prune

Remove abandoned ingestion experiments, stale endpoint probes, obsolete notes,
and duplicate docs.

Purpose:

- Keep raw/bronze source ownership clear.
- Preserve source-faithful raw behavior while removing unsupported experiments.
- Leave the repo easy for future agents to navigate.

Cleanup gate:

- Keep documented supported fallbacks, such as source archives, only when they
  still provide real recovery value.
- Delete or archive stale planning notes that are no longer operationally useful.
- Final repo-wide stale-code and stale-doc pass.

## Follow-Up: Remaining Targeted Cleanup Plan

Status: planned after the aggressive cleanup pass.

This plan covers the work that is still valuable but too broad to compress into
the aggressive deletion pass. The goal is to harden quality observability,
formalize serving stability, finish only the silver modularization that actually
reduces complexity, and clean historical docs/code outside the main pipeline.

Use the same pattern as the previous plans:

1. **Research pass** using the `research-pass` workflow.
2. **Implementation pass**.
3. Verification.
4. Delete stale logic or document the remaining supported fallback.
5. Decide whether an inserted in-between slice is needed.
6. Continue to the next slice unless there is a real blocker or product decision.

### Targeted Slice 1: Quality Athena Registration

Register the current `quality/` S3 outputs as Athena tables with explicit schemas.

Purpose:

- Make quality outputs queryable through Athena instead of only existing as S3
  artifacts.
- Keep quality tables separate from business-facing gold and semantic-gold
  outputs.
- Establish table naming and schema conventions before adding richer checks.

Cleanup gate:

- Delete or replace ad hoc local-only quality inspection commands if the Athena
  tables cover them.
- Document any quality artifact that intentionally remains S3-only.

### Targeted Slice 2: Quality Execution Expansion

Implement the planned quality datasets that are currently mostly manifest-level
intent.

Targets:

- real `grain_checks`
- `row_count_trends`
- `schema_drift`
- richer `anomaly_summaries`
- better source completeness summaries

Purpose:

- Turn quality from a baseline snapshot into ongoing observability.
- Give future refactors a stronger before/after safety net.

Cleanup gate:

- Remove duplicate quality summaries once their signal is represented in the
  quality tables.
- Document any expensive checks that should run on demand instead of every
  pipeline run.

### Targeted Slice 3: Serving Parity Lock

Add formal serving snapshot quality/parity checks similar to the gold parity
lock.

Purpose:

- Prove serving snapshot stability separately from gold table stability.
- Catch missing tables, schema drift, row-count regressions, and freshness issues
  in the DuckDB serving artifact.

Cleanup gate:

- Delete or replace stale serving snapshot spot-check scripts if the parity lock
  covers the same behavior.
- Keep any serving check only when it validates a distinct production risk.

### Targeted Slice 4: Silver Domain Modularization - Easy/Medium

Modularize lower-risk silver scripts where the split is obvious and reduces real
complexity.

Candidate domains:

- schedule
- player movement
- boxscore table family
- matchups
- shot location
- BBR enrichment entrypoints that still have script-level sprawl

Purpose:

- Move parsing, source reads, transforms, quality, and orchestration into clearer
  module boundaries where useful.
- Keep script entrypoints thin.

Cleanup gate:

- Delete duplicated helpers moved into domain modules.
- Keep old entrypoint wrappers only when they remain the supported operational
  command.

### Targeted Slice 5: Silver Domain Modularization - Hard/Event

Modularize the high-complexity silver event stack carefully.

Candidate domains:

- play-by-play events
- pbpstats/event projections
- event context
- on-court state
- possessions and OT fallback
- player/team possession and shot context

Purpose:

- Make event and possession logic easier to reason about.
- Keep domain-specific correctness checks close to the transformation logic.
- Reduce giant-script risk without changing current silver outputs.

Cleanup gate:

- Delete obsolete helper paths after parity checks pass.
- Document any intentionally supported fallback, especially OT possession
  recovery and checkpoint legacy-state fallback.

### Targeted Slice 6: Docs Archive And Runbook Cleanup

Archive stale historical planning docs and tighten the current operational docs.

Purpose:

- Make the repo's "start here" path obvious for future humans and agents.
- Keep historical context without letting old plans look like current truth.

Cleanup gate:

- Move or delete stale plans that are no longer operationally useful.
- Update current runbooks to point at registry, source manifest, quality tables,
  and parity locks.

### Targeted Slice 7: Non-Pipeline Stale-Code Research And Cleanup

Run a separate research and cleanup pass over app/semantic assistant code outside
the raw/silver/gold pipeline.

Purpose:

- Identify stale restrictions, duplicate runtime paths, unused modules, and old
  semantic assistant scaffolding outside the pipeline cleanup scope.
- Keep the product flexible and schema-grounded per the project instructions.

Cleanup gate:

- Delete stale code only after tests or focused verification prove it is no
  longer part of the supported product path.
- If this slice uncovers a larger architectural issue, create a separate plan
  instead of forcing it into this cleanup pass.

## Targeted Cleanup Execution Notes

Status as of 2026-05-11:

- Quality parquet outputs are registered in the separate Athena `quality`
  database.
- Quality baseline execution now writes row-count trends, schema drift, and
  S3-backed grain checks.
- Serving snapshot parity now writes `serving_snapshot_quality` artifacts. The
  configured local DuckDB snapshot path now resolves under this repo at
  `data/serving/nba_serving.duckdb`.
- `player_movement` silver logic is split into domain modules while
  `build_silver_player_movement.py` remains the stable script entrypoint.
- Event-heavy incremental watermark selection is shared through
  `pipelines/athena/transform/silver/incremental_state.py`.
- Historical semantic-gold batch logs are archived under
  `docs/archive/semantic-gold-refactor/`.
- The web/API default question-length cap was removed. Public deployments can
  still opt into a positive `NBA_MAX_QUESTION_CHARS` /
  `PUBLIC_MAX_QUESTION_CHARS` limit for abuse or cost control; the Render
  blueprint now uses `4000` instead of the old `250` cap.

## Final Completion Execution Notes

Status as of 2026-05-11:

- Completion Slice 1 research pass is complete for the event, on-court,
  possession, and context chain.
- Added `pipelines/athena/transform/silver/EVENT_STACK_ARCHITECTURE.md` as the
  durable contract map for future event-stack module splits.
- The event-stack architecture pass was documentation-only. No stale code was
  deleted in this slice because the intended output was a target module-boundary
  note, not a behavior change.
- `pipelines/athena/transform/silver/SILVER_RUNBOOK.md` now points future agents
  to the event-stack contract note before deeper event-domain refactors.
- Completion Slice 2 created the shared `pipelines/athena/transform/silver/boxscore/`
  package for boxscore constants and CDN source helpers.
- The five CDN boxscore transforms now share source listing, JSON reads,
  game-id fallback, timestamp parsing, latest-by-game recency, and core coercion
  helpers through `boxscore.sources`.
- Duplicate CDN helper implementations were removed from the adopted scripts.
  `boxscore_matchups` keeps its distinct endpoint/archive helpers because its
  source shape is materially different.
- Slice 2 verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_boxscore_sources.py pipelines/athena/tests/silver/test_boxscore_schema_order.py pipelines/athena/tests/silver/test_build_silver_boxscore_matchups.py`
  returned 9 passed, and the changed boxscore scripts compiled successfully.
- Completion Slice 3 moved the boxscore game and game-official implementations
  into `boxscore.game` and `boxscore.officials`.
- `build_silver_boxscore_game.py` and
  `build_silver_boxscore_game_official.py` are now stable 19-line wrappers that
  re-export their schemas/helpers and call the package `main()` functions.
- Slice 3 cleanup deleted the old table-scoped implementation bodies from those
  two script files instead of leaving old logic beside new logic.
- Slice 3 verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_boxscore_sources.py pipelines/athena/tests/silver/test_boxscore_schema_order.py pipelines/athena/tests/silver/test_build_silver_boxscore_matchups.py pipelines/athena/tests/silver/test_silver_pipeline_plan.py`
  returned 13 passed, and the package modules plus wrapper scripts compiled
  successfully.
- Completion Slice 4 moved the player-game and team-game boxscore
  implementations into `boxscore.player_game` and `boxscore.team_game`.
- `build_silver_boxscore_player_game.py` and
  `build_silver_boxscore_team_game.py` are now stable thin wrappers while the
  full schema, transform, validation, write, and audit logic lives in the
  package modules.
- Slice 4 cleanup deleted the old implementation bodies from the two top-level
  scripts. The script names remain supported for the silver runner and direct
  targeted backfills.
- Slice 4 verification passed the same 13-test focused suite and compile checks
  for the new package modules plus wrapper scripts.
- Completion Slice 5 moved the team-period and matchups implementations into
  `boxscore.team_period` and `boxscore.matchups`.
- All six top-level boxscore build scripts are now thin, stable entrypoint
  wrappers over the `boxscore` package.
- `boxscore.matchups` intentionally keeps the endpoint/archive-specific source
  handling separate from the shared CDN helpers because its raw sources and
  fallback archive format are different.
- Slice 5 cleanup deleted the old implementation bodies from the remaining two
  top-level scripts. Slice 5 verification passed the 13-test focused suite and
  compile checks for the new modules plus wrappers.
- Completion Slice 6 moved schedule and shot-location implementations into
  `schedule.league` and `shot_location.events`.
- `build_silver_schedule.py` and `build_silver_shot_location_events.py` are now
  stable wrappers. Shot-location still keeps its checkpointed heavy-table
  behavior and source from silver play-by-play unchanged.
- Slice 6 cleanup deleted the old implementation bodies from both top-level
  scripts. Verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_build_silver_shot_location_events.py pipelines/athena/tests/silver/test_silver_pipeline_plan.py`
  returned 9 passed, and the new modules plus wrappers compiled successfully.
- Completion Slice 7 moved the play-by-play implementation into
  `playbyplay.events`; `build_silver_playbyplay_events.py` is now an 11-line
  compatibility wrapper.
- Existing imports of `build_silver_playbyplay_events` remain supported for
  event projection, pbpstats context, possessions, fallback stamping, and parity
  scripts.
- The internal phase helpers are still together inside `playbyplay.events`.
  That is an explicit supported fallback for now: this slice removed the stale
  top-level implementation body and improved navigation, but did not pretend the
  phase-by-phase split is complete.
- Slice 7 verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_incremental_state.py pipelines/athena/tests/silver/test_build_silver_playbyplay_events.py pipelines/athena/tests/silver/test_silver_pipeline_plan.py`
  returned 21 passed, and the package module plus wrapper compiled successfully.
- Completion Slice 8 moved raw-first event projection v2 into
  `event_projection.v2`; `build_silver_event_projection_v2.py` is now an
  11-line compatibility wrapper.
- The move fixed a concrete import/test blocker by making `pbpstats` an explicit
  project dependency in `requirements.txt` and making the moved module's repo-root
  lookup independent of fixed parent counts.
- Event projection v2 still preserves the old import name for parity scripts and
  downstream consumers. The other pbpstats-backed scripts still need their own
  shared loader/config cleanup in Slice 9 and correctness triage in Slice 13.
- Slice 8 verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_build_silver_event_projection_v2.py pipelines/athena/tests/silver/test_build_silver_playbyplay_events.py pipelines/athena/tests/silver/test_silver_pipeline_plan.py`
  returned 26 passed, and the moved modules plus wrappers compiled successfully.
- Completion Slice 9 moved pbpstats projection, pbpstats event context, and
  shared pbpstats helpers into `pbpstats_events.projection_v1`,
  `pbpstats_events.context_v1`, and `pbpstats_events.common`.
- The old `build_silver_pbpstats_event_projection_v1.py`,
  `build_silver_pbpstats_event_context_v1.py`, and
  `pbpstats_projection_common.py` import paths remain supported. The two build
  wrappers alias the old module names to the implementation modules so monkeypatch
  and parity tests still target the real runtime globals.
- Test fixtures no longer hard-code only `reference/pbpstats`; they resolve the
  current local fixture path first and then fall back to `references/` or the old
  `reference/` path.
- Slice 9 verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_build_silver_pbpstats_event_projection_v1.py pipelines/athena/tests/silver/test_build_silver_pbpstats_event_context_v1.py pipelines/athena/tests/silver/test_build_silver_event_projection_v2.py pipelines/athena/tests/silver/test_silver_pipeline_plan.py`
  returned 30 passed, and the pbpstats package modules plus wrappers compiled
  successfully.
- Completion Slice 10 moved the on-court state implementation into
  `on_court.state`; `build_silver_on_court_state.py` is now a stable direct-run
  wrapper and import alias.
- The old import name still resolves to the implementation module, preserving
  public constants and test monkeypatch behavior.
- Slice 10 verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_build_silver_on_court_state.py pipelines/athena/tests/silver/test_silver_pipeline_plan.py`
  returned 18 passed, and the on-court package module plus wrapper compiled
  successfully.
- Completion Slice 11 moved the exact possessions and OT fallback build
  orchestration into `possessions.build` and `possessions.ot_fallback_build`.
- `build_silver_possessions.py` and
  `build_silver_possessions_ot_fallback.py` are now stable direct-run wrappers
  and import aliases over the existing possession package.
- The `pbpstats` dependency made previously failing possession test collection
  healthy again.
- Slice 11 verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_build_silver_possessions.py pipelines/athena/tests/silver/test_build_silver_possessions_ot_fallback.py pipelines/athena/tests/silver/test_possession_pipeline.py pipelines/athena/tests/silver/test_silver_pipeline_plan.py`
  returned 37 passed, and the possession build modules plus wrappers compiled
  successfully.
- Completion Slice 12 moved the player/team context stack into
  `game_context.player_possession`, `game_context.team_possession`,
  `game_context.player_opportunity`, `game_context.player_defensive_shot`, and
  `game_context.team_defensive_shot`.
- The five old `build_silver_*_context.py` scripts are now stable direct-run
  wrappers and import aliases. They support both package imports and direct
  execution from the silver transform directory.
- Slice 12 verification passed:
  `PYTHONPATH=. pytest pipelines/athena/tests/silver/test_build_silver_player_game_possession_context.py pipelines/athena/tests/silver/test_build_silver_team_game_possession_context.py pipelines/athena/tests/silver/test_build_silver_player_game_opportunity_context.py pipelines/athena/tests/silver/test_build_silver_player_game_defensive_shot_context.py pipelines/athena/tests/silver/test_build_silver_team_game_defensive_shot_context.py pipelines/athena/tests/silver/test_silver_pipeline_plan.py`
  returned 31 passed, and the context modules plus wrappers compiled
  successfully.

## Final Pipeline Refactor Completion Plan

Status: forward-looking completion plan.

This 20-slice plan is the remaining work I would want before calling the entire
pipeline refactor complete. It is intentionally more detailed than the earlier
cleanup waves because the remaining work is domain-heavy and correctness
sensitive.

Each slice should follow the same pattern:

1. research pass
2. implementation pass
3. verification
4. stale-code deletion or explicit supported-fallback documentation

### Completion Slice 1: Event Stack Architecture Pass

Read the full event, on-court, possession, and context chain before moving more
code.

Targets:

- `build_silver_playbyplay_events.py`
- `build_silver_event_projection_v2.py`
- `build_silver_pbpstats_event_projection_v1.py`
- `build_silver_pbpstats_event_context_v1.py`
- `build_silver_on_court_state.py`
- possessions and context tables

Output:

- a target module-boundary note for the event stack
- explicit upstream/downstream contracts
- a list of behavior that must remain unchanged

### Completion Slice 2: Boxscore Domain Contracts

Create shared boxscore contracts and source helpers for the boxscore family.

Targets:

- `boxscore_game`
- `boxscore_player_game`
- `boxscore_team_game`
- `boxscore_game_official`
- `boxscore_team_period`
- shared raw CDN boxscore source parsing

Cleanup gate:

- duplicate constants/helpers are removed once the shared contract is adopted

### Completion Slice 3: Boxscore Game And Official Refactor

Modularize the lower-risk boxscore tables first.

Targets:

- `build_silver_boxscore_game.py`
- `build_silver_boxscore_game_official.py`

Expected shape:

- contracts
- sources
- transform
- quality
- pipeline

### Completion Slice 4: Boxscore Player And Team Game Refactor

Split the heavier player/team game boxscore transforms.

Targets:

- `build_silver_boxscore_player_game.py`
- `build_silver_boxscore_team_game.py`

Verification:

- schema-order tests
- quality grain checks
- focused S3-backed row-count/profile checks if needed

### Completion Slice 5: Boxscore Team Period And Matchups Refactor

Finish the remaining boxscore family.

Targets:

- `build_silver_boxscore_team_period.py`
- `build_silver_boxscore_matchups.py`

Cleanup gate:

- one supported runtime path per table
- no duplicate matchups or period helper logic left behind

### Completion Slice 6: Schedule And Shot Location Refactor

Modularize the remaining medium-risk silver tables.

Targets:

- `build_silver_schedule.py`
- `build_silver_shot_location_events.py`

Purpose:

- make source handling, transforms, and validation easy to inspect
- keep silver outputs unchanged

### Completion Slice 7: Play-By-Play Domain Split

Split the largest play-by-play script into durable domain modules.

Targets:

- source loading
- raw/boxscore context
- normalization helpers
- phase enrichment
- row building
- write/audit/checkpoint orchestration

Cleanup gate:

- entrypoint remains stable
- old duplicate helpers are deleted after focused tests pass

### Completion Slice 8: Event Projection V2 Refactor

Modularize event projection v2 while preserving output behavior.

Targets:

- duplicate-action handling
- neighbor links
- lightweight runtime state
- projection row construction
- per-game write/audit behavior

### Completion Slice 9: Pbpstats Projection And Context Refactor

Refactor pbpstats-backed event sidecars together because they share source and
projection assumptions.

Targets:

- `build_silver_pbpstats_event_projection_v1.py`
- `build_silver_pbpstats_event_context_v1.py`
- `pbpstats_projection_common.py`

Cleanup gate:

- shared pbpstats loader/context behavior lives in one place
- reference path handling is corrected or documented

### Completion Slice 10: On-Court State Refactor

Split on-court state into smaller correctness-focused modules.

Targets:

- starter index
- boxscore game index
- substitution clustering
- stint building
- lineup validation
- IO/checkpoint/audit

Verification:

- focused on-court state tests
- quality grain checks for `silver.on_court_state`

### Completion Slice 11: Possessions And OT Fallback Refactor

Clean exact and fallback possession orchestration.

Targets:

- `build_silver_possessions.py`
- `build_silver_possessions_ot_fallback.py`
- `possessions/`

Cleanup gate:

- supported OT fallback behavior is documented
- unsupported fallback/scaffold paths are deleted

### Completion Slice 12: Player And Team Context Refactor

Modularize downstream context tables after the event/possession stack is
stable.

Targets:

- player/team possession context
- player/team defensive shot context
- player opportunity context

Purpose:

- keep boxscore fallback calculations and event-derived calculations easy to
  audit separately

### Completion Slice 13: Correctness Triage

Close known findings surfaced by quality and parity.

Targets:

- serving snapshot path still pointing at old `nba-analytics-lakehouse`
- `reference/pbpstats` vs `references/` path mismatch
- one quality grain duplicate
- 15 missing-column grain checks

Output:

- fix, registry update, or documented real data issue for each finding

### Completion Slice 14: Quality Runner Integration

Make quality table registration and partition refresh part of normal quality
execution.

Targets:

- `run_quality_baseline.py`
- `deploy_quality_tables.py`
- quality README/runbook

Cleanup gate:

- no manual Athena registration step required after quality runs

### Completion Slice 15: Quality Source Completeness Expansion

Add richer source completeness by season and source family.

Targets:

- raw CDN sources
- NBA stats endpoint archives
- BBR raw HTML
- Kaggle/raw CSV sources

Purpose:

- catch missing seasons/source families before silver/gold outputs drift

### Completion Slice 16: Silver-To-Gold Reconciliation

Add stronger reconciliation from silver sources to legacy gold and semantic
gold.

Targets:

- game counts
- player/team game coverage
- season aggregation coverage
- core key lineage

Purpose:

- prove gold stability from the silver layer, not only inside gold

### Completion Slice 17: Serving Cleanup

Fix serving snapshot configuration and decide the supported serving path.

Targets:

- stale snapshot path
- pipeline DuckDB builder
- app-facing gold snapshot scripts
- serving parity lock

Completion bar:

- serving parity returns `ok`
- exactly one supported build/runtime path, or a documented split with clear
  ownership

### Completion Slice 18: Raw/Bronze/Ingestion Cleanup

Normalize ingestion and backfill conventions without changing raw source
faithfulness.

Targets:

- source manifest usage
- season args
- output prefixes
- retry/rate-limit behavior
- raw archive conventions
- reference repo separation

Cleanup gate:

- abandoned probes and one-off endpoint scripts are deleted or documented as
  supported

### Completion Slice 19: Docs And Runbook Finalization

Make current operating truth easy to find.

Targets:

- current pipeline runbooks
- registry docs
- source manifest docs
- quality table docs
- parity commands
- remaining old planning docs

Cleanup gate:

- stale plans are archived when they are no longer operationally useful

### Completion Slice 20: App And Runtime Restriction Cleanup

Review non-pipeline assistant/runtime restrictions against the project rule.

Purpose:

- keep schema/ontology contracts as the primary safety boundary
- remove stale deterministic narrowing when tests prove it is no longer needed

Cleanup gate:

- any remaining restriction above the schema contract must explicitly justify:
  concrete failure prevented, why the schema contract is insufficient, and what
  product flexibility is lost

## Twenty-Slice Execution Notes

### Slice 13: Correctness Triage

Status: completed on 2026-05-11.

Findings addressed:

- The tracked DuckDB serving `.env` path pointed at the old sibling
  `nba-analytics-lakehouse` repo. It now points at this repo's
  `data/serving/nba_serving.duckdb`, and `serving_config.py` normalizes that
  specific stale path back to the current repo default if it reappears.
- Play-by-play parity helpers now prefer `references/pbpstats` while retaining
  `reference/pbpstats` as a legacy fallback. If neither clone exists, they use
  the installed `pbpstats` package.
- Quality grain metadata now matches the actual table contracts for the known
  15 `missing_columns` findings and the `boxscore_team_game` duplicate finding.
  The duplicate was a registry/key issue: the table grain is
  `(gameId, team_side)`, not `(gameId, teamId)`, because two old source games
  have null `teamId` for both sides.

Verification:

- `PYTHONPATH=. pytest pipelines/athena/tests/serving/test_serving_config.py pipelines/athena/tests/test_quality_manifest.py pipelines/athena/tests/test_run_quality_baseline.py`
- `python3 -m py_compile` on the patched parity helpers, serving config, and
  quality manifest.
- Rechecked the same S3 sample parquet objects from the prior quality failure:
  all 15 previous `missing_columns` samples and the previous
  `boxscore_team_game` duplicate sample now resolve without missing columns,
  duplicate grain rows, or null grain rows under the corrected grain keys.

### Slice 14: Quality Runner Integration

Status: completed on 2026-05-11.

Changes:

- `deploy_quality_tables.py` now creates quality tables with
  `CREATE EXTERNAL TABLE IF NOT EXISTS`, reports whether it dropped existing
  tables, and can be used as a non-destructive partition refresh path.
- Added `quality/registration.py` as the shared integration point for normal
  quality runs. It refreshes queryable Athena tables and discovered
  `run_date` partitions with `drop_existing=False`.
- `run_quality_baseline.py`, `gold_parity_lock.py`, and
  `serving_parity_lock.py` now refresh Athena registration after successful S3
  writes by default. Each script supports `--skip-athena-registration` for local
  smoke tests and `--quality-database` for alternate quality databases.
- The quality README now documents that manual deploy is only needed for schema
  reset workflows; normal quality execution handles partition refresh.

Verification:

- `PYTHONPATH=. pytest pipelines/athena/tests/test_deploy_quality_tables.py pipelines/athena/tests/test_run_quality_baseline.py pipelines/athena/tests/test_gold_parity_lock.py pipelines/athena/tests/test_serving_parity_lock.py`
- `python3 -m py_compile` on quality deploy, registration, baseline, gold
  parity, and serving parity modules.

### Slice 15: Quality Source Completeness Expansion

Status: completed on 2026-05-11.

Changes:

- `source_completeness_all_sources` now includes source-family and source-scope
  metadata: `source_family`, `completeness_grain`, `season_year`,
  expected/observed object counts, missing object count, and
  `source_completeness_status`.
- Game- and season-scoped raw sources are grouped by derived NBA season and
  checked against the current refactor backfill window: `2020-21` through
  `2025-26`.
- Source-family inference reuses the ingestion source manifest conventions, so
  CDN, NBA Stats, BBR, hoopR, NBA Data, and Kaggle/raw CSV families are visible
  in quality output.
- The quality deploy spec and README now document the richer source
  completeness table.

Verification:

- `PYTHONPATH=. pytest pipelines/athena/tests/test_run_quality_baseline.py pipelines/athena/tests/test_deploy_quality_tables.py pipelines/ingestion/tests/test_source_manifest.py`
- `python3 -m py_compile pipelines/athena/quality/run_quality_baseline.py pipelines/athena/quality/deploy_quality_tables.py`

### Slice 16: Silver-To-Gold Reconciliation

Status: completed on 2026-05-11.

Changes:

- Added `quality/silver_gold_reconciliation.py`, a dedicated reconciliation
  runner for lineage checks across silver, legacy gold, and semantic gold.
- Added queryable `quality.reconciliation_silver_gold` registration under
  `quality/reconciliation/silver_gold/`.
- Current checks cover:
  - `silver.boxscore_player_game` to `legacy_gold.fct_player_game` row count
    and key coverage
  - non-null `silver.boxscore_team_game` to `legacy_gold.fct_team_game` row
    count and key coverage
  - legacy player/team facts to legacy player/team season aggregates
  - legacy player/team facts to semantic player/team game objects
- The runner writes parquet plus a JSON summary and refreshes Athena quality
  partitions after S3 writes, matching the other quality scripts.

Verification:

- `PYTHONPATH=. pytest pipelines/athena/tests/test_silver_gold_reconciliation.py pipelines/athena/tests/test_deploy_quality_tables.py`
- `python3 -m py_compile pipelines/athena/quality/silver_gold_reconciliation.py pipelines/athena/quality/deploy_quality_tables.py`

### Slice 17: Serving Cleanup

Status: completed on 2026-05-11.

Changes:

- Fixed the tracked DuckDB serving `.env` database from the stale
  `nba_analytics` schema to the real Athena `legacy_gold` schema.
- Documented the current supported split:
  - `pipelines/athena/serving/duckdb/` owns the broader pipeline serving
    snapshot at `data/serving/nba_serving.duckdb`.
  - `scripts/build_gold_slice_snapshot.py` and `scripts/load_gold_snapshot.py`
    remain supported for the app-facing semantic-gold development snapshot
    until the runtime intentionally moves to the broader serving contract.
- Fixed a serving parity false positive: local DuckDB inspection now reads
  column names from `DESCRIBE`, not column types.

Real run:

- First build attempt correctly failed before output because the old configured
  schema `nba_analytics` does not exist in Athena.
- After the config fix, `python3 -m pipelines.athena.serving.duckdb.build_serving_snapshot`
  built `data/serving/nba_serving.duckdb` successfully:
  - 16 required sources
  - latest regular season `2025-26`
  - final snapshot size `58,470,400` bytes
- `python3 pipelines/athena/quality/serving_parity_lock.py` then wrote quality
  output and returned `status_counts: {"ok": 16}`.

Verification:

- `PYTHONPATH=. pytest pipelines/athena/tests/test_serving_parity_lock.py`
- `python3 -m py_compile pipelines/athena/quality/serving_parity_lock.py`
- real DuckDB serving snapshot build and real serving parity lock run

### Slice 18: Raw/Bronze/Ingestion Cleanup

Status: completed on 2026-05-11.

Changes:

- Centralized the current refactor backfill season window in
  `pipelines/ingestion/source_manifest.py` as `DEFAULT_BACKFILL_SEASONS`
  (`2020-21` through `2025-26`).
- `source_manifest.py` now marks game- and season-scoped raw sources with
  `expected_backfill_seasons`, so source ownership and expected coverage can be
  inspected from the manifest.
- Quality source completeness now imports that same ingestion convention instead
  of carrying a duplicate expected-season list.
- Ingestion README now documents the source manifest convention and explicitly
  separates `/references` research clones from operational ingestion code.

Verification:

- `PYTHONPATH=. pytest pipelines/ingestion/tests/test_source_manifest.py pipelines/athena/tests/test_run_quality_baseline.py`
- `python3 -m py_compile pipelines/ingestion/source_manifest.py pipelines/athena/quality/run_quality_baseline.py`

### Slice 19: Docs And Runbook Finalization

Status: completed on 2026-05-11.

Changes:

- Promoted `pipelines/README.md` into the operational front door for the data
  pipeline.
- Added direct pointers to the registry, ingestion source manifest, silver
  runbook, quality README, and serving snapshot contract.
- Added the current command map for source-manifest inspection, silver runs,
  quality baseline, gold parity, silver-to-gold reconciliation, serving parity,
  and DuckDB serving snapshot builds.
- Clarified that long-form plans under `docs/` are project history unless the
  operational README points to them.
- Tightened `docs/archive/README.md` so archived planning docs point back to
  the current operational surfaces and clearly treat `/references` clones as
  research inputs, not ingestion code.

Verification:

- Documentation-only slice; verified with focused `rg`/`sed` inspection rather
  than pipeline tests.

### Slice 20: App And Runtime Restriction Cleanup

Status: completed on 2026-05-11.

Changes:

- Reviewed app/runtime restrictions against the project rule that the
  schema/ontology contract is the primary product boundary.
- Kept the web default unbounded for local/dev question length.
- Raised the Render public deployment question cap from `250` to `4000` for
  both backend `NBA_MAX_QUESTION_CHARS` and frontend
  `PUBLIC_MAX_QUESTION_CHARS`.
- Documented the remaining web-owned gates with explicit justification:
  public debug suppression prevents internal planning/SQL traces from leaking,
  and the optional public request-size cap is an abuse/cost guard rather than a
  semantic support boundary.
- Left ontology/planner result-shape restrictions in place because they are
  contract/runtime truth, not stale web-layer narrowing.

Verification:

- `PYTHONPATH=. pytest tests/test_web_api.py`
- `npm --prefix apps/web-ui test -- --run src/lib/questionLimits.test.ts src/lib/api.test.ts`
