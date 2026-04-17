# Athena `pbpstats` Possessions: Unresolved Games Ledger

## Summary

As of the March 28, 2026 Athena possession backfill and OT fallback passes:

- main `silver/possessions` backfill skipped `87` games where vendored `pbpstats` live possession loading did not produce usable rows
- separate OT fallback recovery under `silver/possessions_ot_fallback/` recovered `47` of those skipped games
- `40` games still remain unresolved

This file is the current ledger for those unresolved games so they can be reviewed later without redoing the clustering work.

## Audit Grounding

Main pbpstats-exact possession backfill:

- audit JSON:
  - `s3://nba-analytics-lakehouse-dev/silver/_audit/possessions/run_date=2026-03-28/possessions_20260328T142847Z_85781dd4.json`
- details JSON:
  - `s3://nba-analytics-lakehouse-dev/silver/_audit/possessions/run_date=2026-03-28/possessions_20260328T142847Z_85781dd4_details.json`

Latest OT fallback rerun after the third OT family:

- audit JSON:
  - `s3://nba-analytics-lakehouse-dev/silver/_audit/possessions_ot_fallback/run_date=2026-03-28/possessions_ot_fallback_20260328T165901Z_877f3e1b.json`

Recovered OT fallback families so far:

- `fallback_ot_carry_forward`: `38`
- `fallback_ot_stale_sub_out_repair`: `6`
- `fallback_ot_end_q4_drift_reconcile`: `3`

## Remaining Unresolved Games

### 1. OT starter-failure games still unresolved (`23`)

These are the remaining overtime games that did not fit the first three clean OT fallback families.

- `0022000545`
- `0022000645`
- `0022100041`
- `0022100353`
- `0022100602`
- `0022100967`
- `0022200025`
- `0022200072`
- `0022200519`
- `0022200748`
- `0022300300`
- `0022300856`
- `0022300893`
- `0022400230`
- `0022400290`
- `0022400771`
- `0022400903`
- `0022401102`
- `0022401162`
- `0041900216`
- `0042000165`
- `0042200214`
- `0042400223`

Current assessment:

- these are now in diminishing-returns territory
- they do not cluster into another high-confidence multi-game OT family yet
- several look more degraded than the first three OT families and are not good candidates for narrow, basketball-plausible recovery rules

### 2. Non-OT starter/reference failures still unresolved (`12`)

These were not part of the OT-only fallback scope and should stay deferred unless a separate clean regulation or non-OT family is identified.

- `0012500014`
- `0022000485`
- `0022100688`
- `0022300765`
- `0032500011`
- `0041900102`
- `0041900112`
- `0041900122`
- `0041900132`
- `0041900142`
- `0041900162`
- `0041900172`

Current assessment:

- these are outside the current OT fallback policy
- they should not be mixed into the OT repair logic
- revisit only if a separate multi-game regulation/reference family emerges

### 3. Malformed reference-event failures still unresolved (`5`)

These are the games where the vendored `pbpstats` reference path itself breaks on malformed or unexpected event shapes.

- `0012100014`
- `0022000511`
- `0022100880`
- `0022200583`
- `0022400322`

Current assessment:

- these are not “normal OT lineup edge cases”
- they should remain skipped unless we deliberately add explicit malformed-event repair logic

## Working Decision

Current recommended policy:

- keep main `silver/possessions` pbpstats-exact
- keep fallback rows separate under `silver/possessions_ot_fallback/`
- do not add more fallback families unless a new rule is:
  - narrow
  - basketball-plausible
  - and worth more than one-off game-by-game repair

If this list is revisited later, start with the `23` unresolved OT games and only continue if a new multi-game family is found.
