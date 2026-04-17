# Silver Parity Remediation Plan

Last updated: March 27, 2026

## Purpose

This document captures the post-migration silver-layer parity gaps surfaced by the strict Athena-vs-Databricks first-10-row spot check.

The check used:

- Athena-side live S3 silver parquet outputs
- Databricks live `nba_analytics.silver.*` tables
- exact schema comparison where possible
- exact first-10-row comparison using stable sort keys per table

The goal of this plan is to separate:

- metadata-only drift
- schema/order drift
- true semantic drift

and then rank the remaining work by downstream importance.

## Spot Check Summary

Silver spot check result:

- `21` mismatches
- `2` metadata-only
- `2` schema/order only
- `17` business-value mismatches

The strict row-level check is intentionally stronger than the earlier migration validation. It surfaces live contract drift even where higher-level parity checks passed.

## Priority Order

### Priority 1: Canonical Event Stream

1. `silver.playbyplay_events`

Why first:

- It is the base semantic event stream.
- Downstream lineup, possession, and pbpstats checks become ambiguous if this layer drifts.
- The current spot check shows drift in core basketball fields such as:
  - `actionNumber`
  - `actionType`
  - `clock`
  - `description`
  - `personId`
  - team/player naming context

Primary fix goal:

- Reconcile live Athena `silver/playbyplay` rows to the Databricks `silver.playbyplay_events` contract and ordered event stream, not just aggregate parity.

### Priority 2: PBPStats Projection Sidecar

2. `silver.pbpstats_event_projection_v1`

Why second:

- It is the pbpstats event-semantic sidecar feeding later lineup/context work.
- The current drift is on real event semantics:
  - `event_num`
  - `event_order`
  - `action_type`
  - `team_id`
  - `offense_team_id`
  - possession-ending flags
  - linked-event references

Primary fix goal:

- Align Athena pbpstats projection output to the live Databricks sidecar row-for-row on the sampled event stream.

### Priority 3: PBPStats Context Sidecar

3. `silver.pbpstats_event_context_v1`

Why third:

- It carries lineup/context state used by later semantic layers.
- The current drift affects:
  - `home_current_player_ids`
  - `away_current_player_ids`
  - `home_lineup_id`
  - `away_lineup_id`
  - `home_fouls_to_give`
  - `away_fouls_to_give`
  - period-starter arrays

Primary fix goal:

- Align lineup/context sidecar semantics after projection parity is stable.

### Priority 4: On-Court State

4. `silver.on_court_state`

Why fourth:

- It depends conceptually on the event and pbpstats layers above.
- It already showed schema-level drift in the spot check.
- Fixing it before the upstream semantic layers would make root-cause analysis noisy.

Primary fix goal:

- Rebuild Athena `on_court_state` against the intended Databricks-aligned semantic path, not the older Athena assumptions.

### Priority 5: Possessions

5. `silver.possessions`

Why fifth:

- It depends on event semantics and lineup context.
- It also showed schema-level drift.
- Possession parity is easier to reason about once the upstream event and lineup layers are clean.

Primary fix goal:

- Reconcile Athena possession output after `playbyplay_events`, `pbpstats_event_projection_v1`, `pbpstats_event_context_v1`, and `on_court_state` are stable.

### Priority 6: Raw-Derived Support Tables

6. `silver.boxscore_game`
7. `silver.boxscore_game_official`
8. `silver.boxscore_team_period`
9. `silver.schedule`

Why after the semantic five:

- These differences matter, but they look more like raw/source-content alignment than derived semantic-model failures.
- Current drift is concentrated in fields such as:
  - local and UTC game time representations
  - week labels
  - arena/location fields
  - official assignment/name fields
  - period score fields

Primary fix goal:

- Normalize the live Athena raw-derived snapshot outputs where they materially affect downstream contracts.

### Priority 7: Basketball Reference / Identity Sidecars

10. `silver.bbr_player_index`
11. `silver.bbr_player_profile`
12. `silver.bbr_player_profile_label_inventory`
13. `silver.player_identity_bridge_bbr_nba`
14. `silver.player_identity_bridge_bbr_nba_ambiguous`
15. `silver.player_identity_bridge_bbr_nba_unmatched_bbr`
16. `silver.player_identity_bridge_bbr_nba_unmatched_nba`
17. `silver.player_movement`

Why later:

- These are not in the core event-to-gold semantic dependency chain.
- Many differences look like source snapshot timing, matching outputs, candidate sets, or source-extracted text drift rather than basketball-event logic drift.

Primary fix goal:

- Decide whether the expected contract is strict Databricks parity or looser source-version parity for these tables.

### Priority 8: Cleanup-Only Drift

18. `silver.players`
19. `silver.team_histories`
20. `silver.boxscore_player_game`
21. `silver.boxscore_team_game`

Why last:

- `players` and `team_histories` are metadata-only drift in the current check.
- `boxscore_player_game` and `boxscore_team_game` showed schema/order-only drift, not immediate business-value drift.

Primary fix goal:

- Clean up metadata and column-order alignment after semantic parity work is complete.

## Bucket Breakdown

### Metadata-Only Drift

- `silver.players`
- `silver.team_histories`

Observed pattern:

- `_meta_pipeline_run_id`
- `_meta_ingested_at_utc`
- `_meta_source_last_modified_utc`

Interpretation:

- These are not current semantic blockers.

### Schema/Order Drift

- `silver.boxscore_player_game`
- `silver.boxscore_team_game`

Interpretation:

- Live schemas or column ordering do not line up, but the spot check did not classify them as immediate business-value drift.

### True Semantic or Contract Drift

Highest-signal semantic layers:

- `silver.playbyplay_events`
- `silver.pbpstats_event_projection_v1`
- `silver.pbpstats_event_context_v1`
- `silver.on_court_state`
- `silver.possessions`

These should be treated as the main silver remediation branch.

### Source-Lineage / Snapshot Drift

Likely dominated by upstream source-version or matching-output differences:

- `silver.bbr_player_index`
- `silver.bbr_player_profile`
- `silver.bbr_player_profile_label_inventory`
- `silver.player_identity_bridge_bbr_nba`
- `silver.player_identity_bridge_bbr_nba_ambiguous`
- `silver.player_identity_bridge_bbr_nba_unmatched_bbr`
- `silver.player_identity_bridge_bbr_nba_unmatched_nba`
- `silver.player_movement`
- parts of `silver.boxscore_game`
- parts of `silver.boxscore_game_official`
- parts of `silver.boxscore_team_period`
- parts of `silver.schedule`

## Recommended Execution Order

1. Focused diff and remediation for `silver.playbyplay_events`
2. Focused diff and remediation for `silver.pbpstats_event_projection_v1`
3. Focused diff and remediation for `silver.pbpstats_event_context_v1`
4. Reconcile `silver.on_court_state`
5. Reconcile `silver.possessions`
6. Normalize raw-derived support tables:
   - `boxscore_game`
   - `boxscore_game_official`
   - `boxscore_team_period`
   - `schedule`
7. Decide strictness expectations for Basketball Reference and identity sidecars
8. Finish metadata/order cleanup

## Working Rule

When the chat history and this document disagree, treat the latest strict spot-check outputs and the current live tables as the source of truth.

The silver remediation branch should optimize for:

- semantic correctness first
- contract parity second
- metadata parity last
