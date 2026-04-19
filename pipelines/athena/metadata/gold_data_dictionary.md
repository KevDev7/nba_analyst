# Gold Layer Data Dictionary

This document reflects the current supported Athena gold surface implemented by the transform scripts under `pipelines/athena/transform/gold/` as of April 7, 2026.

If this file conflicts with the transform scripts under `pipelines/athena/transform/gold/`, treat the transform scripts as the implementation source of truth.

Advanced metric formulas are documented separately in [advanced_metric_formulas.md](pipelines/athena/metadata/advanced_metric_formulas.md).

Registration notes:

- gold Parquet files are written to `s3://nba-analytics-lakehouse-dev/legacy_gold/...` by the table transform scripts
- Athena external table registration is now owned by [deploy_gold_tables.py](/Users/HungNguyen/Desktop/Projects/nba-analytics-lakehouse/pipelines/athena/transform/gold/deploy_gold_tables.py)
- Athena view registration is owned by [deploy_all_views.py](/Users/HungNguyen/Desktop/Projects/nba-analytics-lakehouse/pipelines/athena/transform/gold/deploy_all_views.py)
- the gold player table family is now implemented as one shared package under [player_surface](/Users/HungNguyen/Desktop/Projects/nba-analytics-lakehouse/pipelines/athena/transform/gold/player_surface), with [transform_to_dim_player_parquet.py](/Users/HungNguyen/Desktop/Projects/nba-analytics-lakehouse/pipelines/athena/transform/gold/transform_to_dim_player_parquet.py) and [transform_to_extended_player_dim_parquet.py](/Users/HungNguyen/Desktop/Projects/nba-analytics-lakehouse/pipelines/athena/transform/gold/transform_to_extended_player_dim_parquet.py) acting as thin operational entrypoints
- the Athena catalog currently also contains helper/internal tables such as `_internal`, `_state`, and `boxscore_team_game`; those are intentionally not treated as part of the supported gold serving surface documented here

## Gold Table Inventory

| Table | Grain | Purpose |
| --- | --- | --- |
| `dim_date` | One row per `calendar_date` | Calendar dimension used to join facts to date attributes. |
| `dim_game` | One row per `game_id` | Canonical game dimension with schedule, timing, arena, and matchup context. |
| `dim_player` | One row per `(person_id, player_sk)` with SCD2 versioning semantics | Lean SCD2 player dimension for core warehouse identity and roster context. |
| `extended_player_dim` | One row per `person_id` | Current-state player enrichment table with long-tail profile fields and accepted Basketball Reference linkage. |
| `player_award_history` | One row per matched player-award occurrence | NBA-keyed player honors history projected from Basketball Reference awards and the accepted silver identity bridge. |
| `dim_team` | One row per `(team_id, team_sk)` with SCD2 versioning semantics | SCD2 team dimension that preserves team naming and org context over time. |
| `fct_player_game` | One row per `(game_id, person_id)` | Player-game fact including active, inactive, and DNP rows. |
| `fct_team_game` | One row per `(game_id, team_id)` | Team-game fact at the game summary grain. |
| `fct_player_game_shot_profile_standard` | One row per played `(game_id, person_id)` | Player-game shooting profile fact using the standardized pbpstats shot taxonomy. |
| `fct_player_game_shot_profile_source` | One row per played `(game_id, person_id)` | Player-game shooting profile fact using the source `area` and `areaDetail` NBA zone labels. |
| `fct_player_game_shot_type_source` | One row per played `(game_id, person_id, source_shot_type_key)` | Player-game source shot-style fact using structured `actionType`, `subType`, `descriptor`, and `shotValue` combinations. |
| `agg_player_season` | One row per `(person_id, season_year, raw_season_type_code)` | Season aggregate for player performance. |
| `agg_team_season` | One row per `(team_id, season_year, raw_season_type_code)` | Season aggregate for team performance. |
| `team_season_provenance_sidecar` | One row per `(team_id, season_year, raw_season_type_code)` | Internal team-season provenance sidecar for possession and shot-context coverage counters. |
| `player_season_percentiles` | One row per `(person_id, season_year, raw_season_type_code)` | Curated player-season percentile sidecar for the approved comparison metrics. |
| `team_season_percentiles` | One row per `(team_id, season_year, raw_season_type_code)` | Curated team-season percentile sidecar for the approved comparison metrics. |

Percentiles are materialized as season-grain sidecars rather than added directly onto every existing gold table. That keeps the canonical aggregate surfaces stable while giving serving layers a clean join target for percentile-aware experiences.

## Derived Athena Views

The supported Athena gold view surface is intentionally curated around reusable business-facing views, while per-X player rate math is now handled dynamically at query time. The active deploy entrypoint is [deploy_all_views.py](/Users/HungNguyen/Desktop/Projects/nba-analytics-lakehouse/pipelines/athena/transform/gold/deploy_all_views.py).

Supported views:

- `vw_player_season_boxscore_advanced`
  Curated player-season advanced boxscore view with business-facing column names, boxscore-context rates, rebound percentages, PIE, hybrid possession / defensive-shot metrics, and percentile sibling columns for the curated advanced-metric subset. Provenance and coverage diagnostics are intentionally kept out of this AI-facing view.
- `vw_player_game_shot_type_source`
  Curated player-game serving view for source shot styles such as `2PT Driving Floating Jump Shot` and `3PT Pullup Jump Shot`, with player, matchup, home/away, and shot-type fields already flattened for querying.
- `vw_team_season_boxscore_advanced`
  Curated team-season advanced serving view with `team_id`, season scope, and business-facing `season_type` up front. Its possession family now uses hybrid season totals materialized in `agg_team_season`: `possessions`, `pace`, `turnover_ratio`, `offensive_rating`, `defensive_rating`, `net_rating`, and `steal_percentage` all share the same exact → OT fallback → event-estimated → boxscore-estimated team possession path. `block_percentage` uses the matching clean-path team defensive shot-context ladder materialized into `agg_team_season`, the view continues to use enriched `boxscore_team_game` inputs for bookkeeping-heavy team ratios, and the curated advanced metrics now carry percentile sibling columns from `team_season_percentiles`.

Internal Athena-only debug views:

- `vw_player_season_provenance_debug`
  Internal player-season provenance surface for possession coverage, shot-context coverage, and QA-supporting totals. This view is deployed in Athena but is intentionally not part of the supported AI-facing gold contract.

Removed Athena-only player possession/on-court views are intentionally undocumented here because they are no longer part of the supported pipeline surface.

Deferred / intentionally not deployed views:

- `vw_player_season_pace`
- `vw_player_season_usage`
- `vw_player_season_per_possession`
- `vw_player_season_per_100_possessions`

Retired / intentionally removed view names:

- `vw_team_season_advanced`
- `vw_player_season_rebound_percentages`
- `vw_player_season_pie`
- `vw_player_season_per_minute`
- `vw_player_season_per_30_minutes`
- `vw_player_season_per_40_minutes`
- `vw_player_season_per_48_minutes`
- `vw_player_season_advanced_formulas`
- `vw_player_season_advanced`

## View Column Notes

The supported Athena gold tables below are documented column-by-column. The supported views are defined by the deploy scripts and are partly dynamic:

- `vw_player_season_boxscore_advanced` is a curated serving projection with renamed business-facing columns rather than a passthrough of the base `agg_player_season` schema
  It includes rebound percentages, raw-ratio shot profile fields (`three_point_attempt_rate`, `free_throw_attempt_rate`), PIE, and curated advanced percentile siblings alongside hybrid possession/rating fields while keeping raw season-code and provenance diagnostics internal to the join logic.
- `vw_player_game_shot_type_source` is the curated serving projection for source shot-style labels rather than a passthrough of the base `fct_player_game_shot_type_source` schema
  It adds player name plus matchup/home-away context while preserving the explicit `2PT` / `3PT` source shot labels and the underlying structured shot-type fields.
- `vw_team_season_boxscore_advanced` is the curated team advanced projection documented by the deploy script and formulas doc rather than a static hand-maintained per-column appendix here
  It exposes canonical season labeling through `season_type`, includes raw-ratio shot profile fields (`three_point_attempt_rate`, `free_throw_attempt_rate`), projects curated advanced percentile siblings from `team_season_percentiles`, and keeps raw season-code provenance internal to the join logic.
- `vw_player_season_provenance_debug` is intentionally not part of the supported serving surface
  It exists for warehouse QA and methodology inspection only.

For formulas behind the supported advanced views, see [advanced_metric_formulas.md](pipelines/athena/metadata/advanced_metric_formulas.md).

Player rate stats are no longer materialized as separate Athena views. They are now computed dynamically from `agg_player_season` totals and `seconds_played_total` at query time, which supports arbitrary `per X minutes` requests without expanding the warehouse view surface.

## `dim_date`

Grain: one row per `calendar_date`.

| Column | Type | Description |
| --- | --- | --- |
| `date_sk` | `bigint` | Surrogate key for the calendar date dimension row. |
| `calendar_date` | `date` | Actual calendar date represented by the row. |
| `day_of_week_iso` | `bigint` | ISO weekday number where Monday is 1 and Sunday is 7. |
| `day_name` | `varchar` | Full weekday name for the calendar date. |
| `day_of_month` | `bigint` | Day number within the month. |
| `day_of_year` | `bigint` | Day number within the year. |
| `week_of_year` | `bigint` | Calendar week number within the year. |
| `month_num` | `bigint` | Numeric month value from 1 to 12. |
| `month_name` | `varchar` | Full month name. |
| `quarter_num` | `bigint` | Calendar quarter number from 1 to 4. |
| `year_num` | `bigint` | Four-digit calendar year. |
| `nba_week_number` | `bigint` | NBA-specific week number from schedule data when available. |
| `nba_week_name` | `varchar` | NBA-specific week label from schedule data when available. |
| `is_weekend` | `boolean` | True when the date falls on a weekend. |
| `is_month_start` | `boolean` | True when the date is the first day of a month. |
| `is_month_end` | `boolean` | True when the date is the last day of a month. |
| `is_quarter_start` | `boolean` | True when the date is the first day of a quarter. |
| `is_quarter_end` | `boolean` | True when the date is the last day of a quarter. |
| `is_year_start` | `boolean` | True when the date is January 1. |
| `is_year_end` | `boolean` | True when the date is December 31. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |

## `dim_game`

Grain: one row per `game_id`.

| Column | Type | Description |
| --- | --- | --- |
| `game_sk` | `bigint` | Surrogate key for the game dimension row. |
| `game_id` | `varchar` | NBA natural game identifier. |
| `season_year` | `varchar` | Season label such as `2024-25`. |
| `season_start_year` | `bigint` | Numeric start year for the season label. |
| `raw_season_type_code` | `varchar` | Raw NBA season type code derived from the game identifier. |
| `season_type` | `varchar` | Season type label such as `regular_season` or `playoffs`. |
| `league_id` | `varchar` | League identifier from the upstream schedule source. |
| `game_code` | `varchar` | Alternate game code from source systems. |
| `game_sequence` | `bigint` | Sequence number for the game within the schedule feed. |
| `game_date` | `date` | Local game date used for warehouse joins. |
| `game_datetime_utc` | `timestamp(3)` | Canonical UTC start timestamp for the game. |
| `local_market_game_datetime_utc` | `timestamp(3)` | Arena-local game time normalized to UTC. |
| `home_market_game_datetime_utc` | `timestamp(3)` | Home-market game time normalized to UTC. |
| `away_market_game_datetime_utc` | `timestamp(3)` | Away-market game time normalized to UTC. |
| `eastern_time_game_datetime_utc` | `timestamp(3)` | Eastern Time game timestamp normalized to UTC. |
| `game_status_code` | `bigint` | Numeric status code from the source feed. |
| `game_status_text` | `varchar` | Human-readable game status label. |
| `postponed_status` | `varchar` | Postponement status when the game is delayed or rescheduled. |
| `is_if_necessary` | `boolean` | True when the game is marked "if necessary" in a series. |
| `game_label` | `varchar` | Primary schedule label for the game. |
| `game_sublabel` | `varchar` | Secondary schedule label for the game. |
| `game_subtype` | `varchar` | Source subtype for the game event. |
| `series_game_number` | `varchar` | Game number within a playoff or tournament series. |
| `series_text` | `varchar` | Series context text from the schedule feed. |
| `is_neutral_site` | `boolean` | True when the game is played at a neutral site. |
| `duration_minutes` | `bigint` | Reported game duration in minutes. |
| `attendance` | `bigint` | Reported game attendance. |
| `is_sellout` | `boolean` | True when the source marks the game as a sellout. |
| `regulation_periods` | `bigint` | Number of regulation periods defined for the game. |
| `current_period` | `bigint` | Current or final period number from the game feed. |
| `game_clock` | `varchar` | Clock value reported with the current period. |
| `arena_id` | `bigint` | Arena identifier from upstream source data. |
| `arena_name` | `varchar` | Arena name. |
| `arena_city` | `varchar` | Arena city. |
| `arena_state` | `varchar` | Arena state or province. |
| `arena_country` | `varchar` | Arena country. |
| `arena_timezone` | `varchar` | Arena timezone label from the source feed. |
| `home_team_id` | `bigint` | Natural team ID for the home team. |
| `away_team_id` | `bigint` | Natural team ID for the away team. |
| `home_team_name` | `varchar` | Home team name at game time. |
| `away_team_name` | `varchar` | Away team name at game time. |
| `home_team_city` | `varchar` | Home team city at game time. |
| `away_team_city` | `varchar` | Away team city at game time. |
| `home_team_abbreviation` | `varchar` | Home team tricode at game time. |
| `away_team_abbreviation` | `varchar` | Away team tricode at game time. |
| `home_team_slug` | `varchar` | Home team slug from the schedule feed. |
| `away_team_slug` | `varchar` | Away team slug from the schedule feed. |
| `source_meta_version` | `bigint` | Source metadata version captured from box score feed. |
| `source_meta_code` | `bigint` | Source metadata status code captured from box score feed. |
| `source_request` | `varchar` | Source request identifier or endpoint marker. |
| `source_meta_time_utc` | `timestamp(3)` | Source metadata timestamp normalized to UTC. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |

## `dim_player`

Grain: one row per `(person_id, player_sk)` with SCD2 versioning semantics.

Join guidance:

- `dim_player` is an SCD2 history dimension, not a one-row-per-`person_id` lookup surface.
- Player analytics joins should use warehouse surrogate keys instead of joining this table directly on `person_id`.
- For game-grain analytics, join `fct_player_game.player_sk` to `dim_player.player_sk`.
- For player season aggregates, join `agg_player_season.current_player_sk` to `dim_player.player_sk`.
- Use `extended_player_dim` only for current-state enrichment that is intentionally one row per `person_id`.

| Column | Type | Description |
| --- | --- | --- |
| `player_sk` | `bigint` | Surrogate key for the player dimension version. |
| `person_id` | `bigint` | NBA natural player identifier. |
| `player_name` | `varchar` | Full player name from source systems. |
| `first_name` | `varchar` | Player first name. |
| `family_name` | `varchar` | Player last name or family name. |
| `display_name` | `varchar` | Preferred player display name used by the app. |
| `primary_position` | `varchar` | Most specific position value captured for the version. |
| `latest_team_id` | `bigint` | Latest observed team ID for the version, including non-NBA teams if present. |
| `latest_nba_team_id` | `bigint` | Latest observed current NBA team ID when the player is tied to an NBA franchise. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `valid_from_utc` | `timestamp(3)` | UTC timestamp when this SCD2 version becomes valid. |
| `valid_to_utc` | `timestamp(3)` | UTC timestamp when this SCD2 version stops being valid. |
| `is_current` | `bigint` | Current-version flag stored as `1` or `0`. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |
| `birth_date` | `date` | Player birth date when available from the silver player bio source. |
| `school` | `varchar` | School or college listed in the player bio source. |
| `country` | `varchar` | Country listed in the player bio source. |
| `height_inches` | `bigint` | Player height in inches from the player bio source. |
| `weight_lbs` | `bigint` | Player listed playing weight in pounds from the player bio source. |
| `draft_year` | `bigint` | Draft year from the player bio source when the player was drafted. |
| `draft_round` | `bigint` | Draft round from the player bio source when the player was drafted. |
| `draft_number` | `bigint` | Draft pick number from the player bio source when the player was drafted. |

## `extended_player_dim`

Grain: one row per `person_id` in the current gold player population.

| Column | Type | Description |
| --- | --- | --- |
| `person_id` | `bigint` | NBA natural player identifier. |
| `player_name_short` | `varchar` | Alternate short-name format from the source feed. |
| `latest_jersey_number` | `varchar` | Latest observed jersey number from the source player-game feed. |
| `latest_status` | `varchar` | Latest observed roster or availability status from the source player-game feed. |
| `position_group` | `varchar` | Normalized position bucket such as guard, wing, or big. |
| `first_seen_game_date` | `date` | First game date observed for the player in source history. |
| `last_seen_game_date` | `date` | Most recent game date observed for the player in source history. |
| `first_season_played` | `varchar` | First observed season label in warehouse game history for the player, such as `2022-23`. |
| `last_season_played` | `varchar` | Most recent observed season label in warehouse game history where the player appeared, such as `2025-26`. |
| `is_guard` | `bigint` | Source guard flag stored as `1` or `0` when available. |
| `is_forward` | `bigint` | Source forward flag stored as `1` or `0` when available. |
| `is_center` | `bigint` | Source center flag stored as `1` or `0` when available. |
| `basketball_reference_player_id` | `varchar` | Accepted Basketball Reference player identifier from the silver identity bridge when one exists for the gold player row. |
| `bbr_match_method` | `varchar` | Accepted bridge match method used to link the NBA player ID to Basketball Reference. |
| `bbr_match_confidence` | `double` | Confidence score from the accepted Basketball Reference bridge match. |
| `bbr_profile_url` | `varchar` | Canonical Basketball Reference profile URL. |
| `bbr_formal_name` | `varchar` | Formal or expanded player name from Basketball Reference. |
| `bbr_pronunciation` | `varchar` | Pronunciation text captured from the Basketball Reference player profile. |
| `bbr_former_name_note` | `varchar` | Former-name note from Basketball Reference when the player profile records one. |
| `bbr_nicknames_raw` | `varchar` | Raw nickname text from Basketball Reference. |
| `bbr_instagram_handle` | `varchar` | Instagram handle captured from Basketball Reference when present. |
| `bbr_position_raw` | `varchar` | Raw position text from Basketball Reference. |
| `bbr_shoots` | `varchar` | Shooting handedness from Basketball Reference. |
| `bbr_height_raw` | `varchar` | Raw height string from Basketball Reference such as `6-9`. |
| `bbr_height_cm` | `bigint` | Height in centimeters from Basketball Reference. |
| `bbr_weight_kg` | `bigint` | Weight in kilograms from Basketball Reference. |
| `bbr_current_team_raw` | `varchar` | Raw current-team text from Basketball Reference. |
| `bbr_birth_place_raw` | `varchar` | Raw birthplace text from Basketball Reference. |
| `bbr_birth_country_code` | `varchar` | Birth-country code from Basketball Reference. |
| `bbr_death_date` | `date` | Death date from Basketball Reference when applicable. |
| `bbr_college_raw` | `varchar` | Primary college text from Basketball Reference. |
| `bbr_colleges_raw` | `varchar` | Multi-school college text from Basketball Reference when present. |
| `bbr_high_school_raw` | `varchar` | Primary high-school text from Basketball Reference. |
| `bbr_high_schools_raw` | `varchar` | Multi-school high-school text from Basketball Reference when present. |
| `bbr_recruiting_rank_raw` | `varchar` | Raw recruiting-rank text from Basketball Reference. |
| `bbr_recruiting_rank_year` | `bigint` | Recruiting ranking year from Basketball Reference. |
| `bbr_recruiting_rank_ordinal` | `bigint` | Recruiting rank ordinal value from Basketball Reference. |
| `bbr_relatives_raw` | `varchar` | Raw relatives/family text from Basketball Reference. |
| `bbr_draft_raw` | `varchar` | Raw draft text from Basketball Reference. |
| `bbr_draft_team_raw` | `varchar` | Draft-team text from Basketball Reference. |
| `draft_team_id` | `bigint` | Canonical current-franchise NBA team ID mapped from the Basketball Reference draft-team text when the drafting franchise has a present-day NBA equivalent. |
| `bbr_draft_pick_in_round` | `bigint` | Draft pick number within the round from Basketball Reference. |
| `bbr_draft_league` | `varchar` | Draft league label from Basketball Reference. |
| `bbr_draft_selection_note` | `varchar` | Draft selection note from Basketball Reference. |
| `bbr_nba_debut_date` | `date` | NBA debut date from Basketball Reference. |
| `bbr_aba_debut_date` | `date` | ABA debut date from Basketball Reference when applicable. |
| `bbr_experience_years` | `bigint` | Reported years of experience from Basketball Reference. |
| `bbr_career_length_years` | `bigint` | Reported career length in years from Basketball Reference. |
| `bbr_hall_of_fame_flag` | `bigint` | Hall of Fame flag from Basketball Reference stored as `1` or `0` when present. |
| `bbr_hall_of_fame_role` | `varchar` | Hall of Fame role label from Basketball Reference. |
| `bbr_hall_of_fame_year` | `bigint` | Hall of Fame induction year from Basketball Reference. |
| `bbr_hall_of_fame_raw` | `varchar` | Raw Hall of Fame text from Basketball Reference. |
| `bbr_headshot_url` | `varchar` | Basketball Reference headshot URL. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |

## `player_award_history`

Grain: one row per matched player-award occurrence.

Design notes:

- This table is sourced from `silver/bbr_player_awards` joined to `silver/player_identity_bridge_bbr_nba`.
- It keeps the existing bridge scope rather than trimming to the current gold player population.
- It keeps only `NBA` award rows from the silver awards source before projecting into gold.
- `person_id` is the NBA natural player identifier carried through the accepted silver bridge.
- `team_tier` is populated only for league-team honors like `All-NBA`, `All-Defensive`, and `All-Rookie`.
- The gold surface is intentionally lean and keeps only normalized award facts plus standard warehouse metadata.

| Column | Type | Description |
| --- | --- | --- |
| `player_award_history_sk` | `bigint` | Surrogate key for the player-award history row. |
| `person_id` | `bigint` | NBA natural player identifier from the accepted Basketball Reference bridge. |
| `award_type` | `varchar` | Normalized award type such as `mvp`, `finals_mvp`, `dpoy`, `all_star`, `all_nba`, `all_defensive`, or `all_rookie`. |
| `season_year` | `varchar` | Canonical season label for the award occurrence, such as `2021-22`. |
| `team_tier` | `bigint` | Team tier for league-team honors when present, such as `1`, `2`, or `3`. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |

## `dim_team`

Grain: one row per `(team_id, team_sk)` with SCD2 versioning semantics.

| Column | Type | Description |
| --- | --- | --- |
| `team_sk` | `bigint` | Surrogate key for the team dimension version. |
| `team_id` | `bigint` | NBA natural team identifier. |
| `team_name` | `varchar` | Team name for the version. |
| `team_city` | `varchar` | Team city for the version. |
| `team_abbreviation` | `varchar` | Three-letter team code for the version. |
| `team_slug` | `varchar` | Team slug from the schedule feed. |
| `first_seen_game_date` | `date` | First game date observed for the team in source history. |
| `last_seen_game_date` | `date` | Most recent game date observed for the team in source history. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `valid_from_utc` | `timestamp(3)` | UTC timestamp when this SCD2 version becomes valid. |
| `valid_to_utc` | `timestamp(3)` | UTC timestamp when this SCD2 version stops being valid. |
| `is_current` | `bigint` | Current-version flag stored as `1` or `0`. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |
| `conference` | `varchar` | Current or inferred conference assignment for NBA franchises. |
| `division` | `varchar` | Current or inferred division assignment for NBA franchises. |

## `fct_player_game`

Grain: one row per `(game_id, person_id)`.

| Column | Type | Description |
| --- | --- | --- |
| `fct_player_game_sk` | `bigint` | Surrogate key for the player-game fact row. |
| `game_sk` | `bigint` | Foreign key to [`dim_game`](#dim_game). |
| `date_sk` | `bigint` | Foreign key to [`dim_date`](#dim_date). |
| `player_sk` | `bigint` | Point-in-time foreign key to [`dim_player`](#dim_player). |
| `team_sk` | `bigint` | Point-in-time foreign key to [`dim_team`](#dim_team). |
| `game_id` | `varchar` | NBA natural game identifier. |
| `person_id` | `bigint` | NBA natural player identifier. |
| `team_id` | `bigint` | Natural team identifier for the player's team in that game. |
| `game_datetime_utc` | `timestamp(3)` | Canonical UTC game start timestamp. |
| `game_date` | `date` | Local game date used for reporting and joins. |
| `season_year` | `varchar` | Season label such as `2024-25`. |
| `season_start_year` | `bigint` | Numeric start year for the season label. |
| `raw_season_type_code` | `varchar` | Raw NBA season type code derived from the game identifier. |
| `season_type` | `varchar` | Season type label such as `regular_season` or `playoffs`. |
| `team_side` | `varchar` | Team role in the game, typically home or away. |
| `player_position` | `varchar` | Position assigned to the player for that game. |
| `player_status` | `varchar` | Game-specific availability or participation status. |
| `player_order` | `bigint` | Source order value for the player within the box score feed. |
| `is_starter` | `bigint` | Starter flag stored as `1` or `0`. |
| `is_on_court` | `bigint` | On-court flag from source data, stored as `1` or `0` when available. |
| `did_play` | `bigint` | Played flag stored as `1` or `0`, including DNP rows when `0`. |
| `minutes_raw` | `varchar` | Raw minutes string from the source feed. |
| `minutes_calculated_raw` | `varchar` | Calculated duration string from the source feed when supplied. |
| `raw_plus_value` | `bigint` | Raw plus value from the box score feed. |
| `raw_minus_value` | `bigint` | Raw minus value from the box score feed. |
| `plus_minus_points` | `bigint` | Net point differential while the player was on the floor. |
| `assists` | `bigint` | Assists recorded for the player in the game. |
| `blocks` | `bigint` | Blocks recorded for the player in the game. |
| `blocks_received` | `bigint` | Times the player's shots were blocked in the game. |
| `field_goals_attempted` | `bigint` | Total field goal attempts. |
| `field_goals_made` | `bigint` | Total field goals made. |
| `field_goals_percentage` | `double` | Field goal percentage for the game. |
| `fouls_offensive` | `bigint` | Offensive fouls committed. |
| `fouls_drawn` | `bigint` | Fouls drawn by the player. |
| `fouls_personal` | `bigint` | Personal fouls committed. |
| `fouls_technical` | `bigint` | Technical fouls committed. |
| `free_throws_attempted` | `bigint` | Total free throw attempts. |
| `free_throws_made` | `bigint` | Total free throws made. |
| `free_throws_percentage` | `double` | Free throw percentage for the game. |
| `rebounds_defensive` | `bigint` | Defensive rebounds recorded. |
| `rebounds_offensive` | `bigint` | Offensive rebounds recorded. |
| `rebounds_total` | `bigint` | Total rebounds recorded. |
| `steals` | `bigint` | Steals recorded. |
| `turnovers` | `bigint` | Turnovers committed. |
| `points` | `bigint` | Points scored. |
| `three_pointers_attempted` | `bigint` | Three-point attempts. |
| `three_pointers_made` | `bigint` | Three-pointers made. |
| `three_pointers_percentage` | `double` | Three-point percentage for the game. |
| `two_pointers_attempted` | `bigint` | Two-point attempts. |
| `two_pointers_made` | `bigint` | Two-pointers made. |
| `two_pointers_percentage` | `double` | Two-point percentage for the game. |
| `points_fast_break` | `bigint` | Fast-break points scored by the player. |
| `points_in_the_paint` | `bigint` | Points scored in the paint. |
| `points_second_chance` | `bigint` | Second-chance points scored. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |
| `seconds_played_total` | `double` | Minutes played converted to total seconds. |
| `minutes_played_decimal` | `double` | Minutes played converted to decimal minutes. |

## `fct_team_game`

Grain: one row per `(game_id, team_id)`.

| Column | Type | Description |
| --- | --- | --- |
| `fct_team_game_sk` | `bigint` | Surrogate key for the team-game fact row. |
| `game_sk` | `bigint` | Foreign key to [`dim_game`](#dim_game). |
| `date_sk` | `bigint` | Foreign key to [`dim_date`](#dim_date). |
| `team_sk` | `bigint` | Point-in-time foreign key to [`dim_team`](#dim_team) for the team. |
| `opponent_team_sk` | `bigint` | Point-in-time foreign key to [`dim_team`](#dim_team) for the opponent. |
| `game_id` | `varchar` | NBA natural game identifier. |
| `team_id` | `bigint` | Natural team identifier for the team row. |
| `opponent_team_id` | `bigint` | Natural team identifier for the opponent. |
| `game_datetime_utc` | `timestamp(3)` | Canonical UTC game start timestamp. |
| `game_date` | `date` | Local game date used for reporting and joins. |
| `season_year` | `varchar` | Season label such as `2024-25`. |
| `season_start_year` | `bigint` | Numeric start year for the season label. |
| `raw_season_type_code` | `varchar` | Raw NBA season type code derived from the game identifier. |
| `season_type` | `varchar` | Season type label such as `regular_season` or `playoffs`. |
| `team_side` | `varchar` | Team role in the game, typically home or away. |
| `is_home_team` | `bigint` | Home-team flag stored as `1` or `0`. |
| `team_name` | `varchar` | Team name at game time. |
| `team_city` | `varchar` | Team city at game time. |
| `team_abbreviation` | `varchar` | Team tricode at game time. |
| `opponent_team_name` | `varchar` | Opponent team name at game time. |
| `opponent_team_city` | `varchar` | Opponent team city at game time. |
| `opponent_team_abbreviation` | `varchar` | Opponent team tricode at game time. |
| `score` | `bigint` | Points scored by the team in the game. |
| `opponent_score` | `bigint` | Points scored by the opponent in the game. |
| `point_diff` | `bigint` | Team score minus opponent score. |
| `is_in_bonus` | `bigint` | Bonus-state indicator from the source feed. |
| `timeouts_remaining` | `bigint` | Timeouts remaining as reported in the source feed. |
| `seconds_played_total` | `double` | Team total minutes in seconds, aggregated from player-game rows for the same game and team. |
| `minutes_played_decimal` | `double` | Team total minutes in decimal form. |
| `assists` | `bigint` | Team assists aggregated from player-game rows. |
| `blocks` | `bigint` | Team blocks aggregated from player-game rows. |
| `blocks_received` | `bigint` | Team shots blocked against the team, aggregated from player-game rows. |
| `field_goals_attempted` | `bigint` | Team field goal attempts aggregated from player-game rows. |
| `field_goals_made` | `bigint` | Team field goals made aggregated from player-game rows. |
| `field_goals_percentage` | `double` | Team field goal percentage derived from makes and attempts. |
| `fouls_offensive` | `bigint` | Team offensive fouls aggregated from player-game rows. |
| `fouls_drawn` | `bigint` | Fouls drawn by the team, aggregated from player-game rows. |
| `fouls_personal` | `bigint` | Team personal fouls aggregated from player-game rows. |
| `fouls_technical` | `bigint` | Team technical fouls aggregated from player-game rows. |
| `free_throws_attempted` | `bigint` | Team free throw attempts aggregated from player-game rows. |
| `free_throws_made` | `bigint` | Team free throws made aggregated from player-game rows. |
| `free_throws_percentage` | `double` | Team free throw percentage derived from makes and attempts. |
| `rebounds_defensive` | `bigint` | Team defensive rebounds aggregated from player-game rows. |
| `rebounds_offensive` | `bigint` | Team offensive rebounds aggregated from player-game rows. |
| `rebounds_total` | `bigint` | Team total rebounds aggregated from player-game rows. |
| `steals` | `bigint` | Team steals aggregated from player-game rows. |
| `turnovers` | `bigint` | Team turnovers aggregated from player-game rows. |
| `three_pointers_attempted` | `bigint` | Team three-point attempts aggregated from player-game rows. |
| `three_pointers_made` | `bigint` | Team three-pointers made aggregated from player-game rows. |
| `three_pointers_percentage` | `double` | Team three-point percentage derived from makes and attempts. |
| `two_pointers_attempted` | `bigint` | Team two-point attempts aggregated from player-game rows. |
| `two_pointers_made` | `bigint` | Team two-pointers made aggregated from player-game rows. |
| `two_pointers_percentage` | `double` | Team two-point percentage derived from makes and attempts. |
| `points_fast_break` | `bigint` | Team fast-break points aggregated from player-game rows. |
| `points_in_the_paint` | `bigint` | Team paint points aggregated from player-game rows. |
| `points_second_chance` | `bigint` | Team second-chance points aggregated from player-game rows. |
| `is_win` | `bigint` | Win flag stored as `1` or `0`. |
| `is_loss` | `bigint` | Loss flag stored as `1` or `0`. |
| `is_tie` | `bigint` | Tie flag stored as `1` or `0`. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |

## `fct_player_game_shot_profile_standard`

Grain: one row per played `(game_id, person_id)` where the base player-game row has `did_play = 1`.

Identity and context columns:
- `fct_player_game_shot_profile_standard_sk`
- `fct_player_game_sk`
- `game_sk`, `date_sk`, `player_sk`, `team_sk`, `opponent_team_sk`
- `game_id`, `person_id`, `team_id`, `opponent_team_id`
- `game_datetime_utc`, `game_date`
- `season_year`, `season_start_year`, `raw_season_type_code`, `season_type`

Overall shooting columns:
- `field_goals_attempted`
- `field_goals_made`
- `three_pointers_attempted`
- `three_pointers_made`
- `points_from_field_goals`

Standardized shot-profile bucket columns:
- `at_rim_field_goals_attempted`, `at_rim_field_goals_made`
- `short_mid_range_field_goals_attempted`, `short_mid_range_field_goals_made`
- `long_mid_range_field_goals_attempted`, `long_mid_range_field_goals_made`
- `corner_3_field_goals_attempted`, `corner_3_field_goals_made`
- `arc_3_field_goals_attempted`, `arc_3_field_goals_made`
- `unknown_distance_2pt_field_goals_attempted`, `unknown_distance_2pt_field_goals_made`

Metadata columns:
- `record_source`
- `created_at_utc`
- `updated_at_utc`

Notes:
- This table uses `silver/pbpstats_event_projection_v1` as the standardized shot-zone source.
- Totals are derived from the same field-goal event stream as the bucket columns, so bucket sums reconcile to the table-level field-goal totals.

## `fct_player_game_shot_profile_source`

Grain: one row per played `(game_id, person_id)` where the base player-game row has `did_play = 1`.

Identity and context columns:
- `fct_player_game_shot_profile_source_sk`
- `fct_player_game_sk`
- `game_sk`, `date_sk`, `player_sk`, `team_sk`, `opponent_team_sk`
- `game_id`, `person_id`, `team_id`, `opponent_team_id`
- `game_datetime_utc`, `game_date`
- `season_year`, `season_start_year`, `raw_season_type_code`, `season_type`

Overall shooting columns:
- `field_goals_attempted`
- `field_goals_made`
- `three_pointers_attempted`
- `three_pointers_made`
- `points_from_field_goals`

Source `area` bucket columns:
- `restricted_area_field_goals_attempted`, `restricted_area_field_goals_made`
- `paint_non_restricted_area_field_goals_attempted`, `paint_non_restricted_area_field_goals_made`
- `mid_range_field_goals_attempted`, `mid_range_field_goals_made`
- `left_corner_3_field_goals_attempted`, `left_corner_3_field_goals_made`
- `right_corner_3_field_goals_attempted`, `right_corner_3_field_goals_made`
- `above_the_break_3_field_goals_attempted`, `above_the_break_3_field_goals_made`

Source `areaDetail` bucket columns:
- `center_0_8_field_goals_attempted`, `center_0_8_field_goals_made`
- `left_8_16_field_goals_attempted`, `left_8_16_field_goals_made`
- `center_8_16_field_goals_attempted`, `center_8_16_field_goals_made`
- `right_8_16_field_goals_attempted`, `right_8_16_field_goals_made`
- `left_16_24_field_goals_attempted`, `left_16_24_field_goals_made`
- `left_center_16_24_field_goals_attempted`, `left_center_16_24_field_goals_made`
- `center_16_24_field_goals_attempted`, `center_16_24_field_goals_made`
- `right_center_16_24_field_goals_attempted`, `right_center_16_24_field_goals_made`
- `right_16_24_field_goals_attempted`, `right_16_24_field_goals_made`
- `left_24_plus_field_goals_attempted`, `left_24_plus_field_goals_made`
- `left_center_24_plus_field_goals_attempted`, `left_center_24_plus_field_goals_made`
- `center_24_plus_field_goals_attempted`, `center_24_plus_field_goals_made`
- `right_center_24_plus_field_goals_attempted`, `right_center_24_plus_field_goals_made`
- `right_24_plus_field_goals_attempted`, `right_24_plus_field_goals_made`
- `unmapped_source_area_field_goals_attempted`, `unmapped_source_area_field_goals_made`
- `unmapped_source_area_detail_field_goals_attempted`, `unmapped_source_area_detail_field_goals_made`

Metadata columns:
- `record_source`
- `created_at_utc`
- `updated_at_utc`

Notes:
- This table uses `silver/playbyplay` source labels directly.
- `area` and `areaDetail` bucket families coexist in the same player-game row so downstream queries can use either the coarser NBA-native zones or the finer source detail geography without re-aggregating play-by-play events.
- The `unmapped_source_area*` buckets capture shots where the raw feed did not provide a supported `area` or `areaDetail` label, which keeps the table-level field-goal totals reconcilable even when historical source zoning coverage is incomplete.

## `fct_player_game_shot_type_source`

Grain: one row per played `(game_id, person_id, source_shot_type_key)` where the base player-game row has `did_play = 1`.

Identity and context columns:
- `fct_player_game_shot_type_source_sk`
- `fct_player_game_sk`
- `game_sk`, `date_sk`, `player_sk`, `team_sk`, `opponent_team_sk`
- `game_id`, `person_id`, `team_id`, `opponent_team_id`
- `game_datetime_utc`, `game_date`
- `season_year`, `season_start_year`, `raw_season_type_code`, `season_type`

Shot-type descriptor columns:
- `source_shot_type_key`
- `source_shot_type_label`
- `source_shot_type_family`
- `action_type`
- `sub_type`
- `descriptor`
- `shot_value`
- `is_two_point_shot`
- `is_three_point_shot`

Shot production columns:
- `field_goals_attempted`
- `field_goals_made`
- `three_pointers_attempted`
- `three_pointers_made`
- `points_from_field_goals`

Metadata columns:
- `record_source`
- `created_at_utc`
- `updated_at_utc`

Notes:
- This table uses `silver/playbyplay` source shot labels directly, keeping the structured `actionType`, `subType`, `descriptor`, and `shotValue` combination instead of collapsing to broader zone buckets.
- The user-facing `source_shot_type_label` is generated from those structured fields and always prefixes the shot with `2PT` or `3PT`, which keeps labels like `2PT Driving Floating Jump Shot` and `3PT Pullup Jump Shot` distinct.
- `source_shot_type_family` is the coarse grouped family for downstream analytics, so source variants such as `Jump Shot` and `jumpshot` are normalized to the same family label.
- The fact is intentionally denormalized so LLM-facing serving surfaces do not need a separate shot-type dimension join just to recover the human-readable label.

## `agg_player_season`

Grain: one row per `(person_id, season_year, raw_season_type_code)`.

| Column | Type | Description |
| --- | --- | --- |
| `agg_player_season_sk` | `bigint` | Surrogate key for the player-season aggregate row. |
| `person_id` | `bigint` | NBA natural player identifier. |
| `current_player_sk` | `bigint` | Current player surrogate key joined for the player. |
| `season_year` | `varchar` | Season label such as `2024-25`. |
| `season_start_year` | `bigint` | Numeric start year for the season label. |
| `raw_season_type_code` | `varchar` | Raw NBA season type code derived from game IDs. |
| `season_type` | `varchar` | Season type label such as `regular_season` or `playoffs`. |
| `age_on_jan_31` | `bigint` | Player age in completed years on January 31 of `season_start_year + 1`, matching the Basketball Reference season-age convention and giving one stable season-level age value. |
| `primary_team_id` | `bigint` | Dominant or primary team ID for the player's season slice. |
| `primary_team_abbreviation` | `varchar` | Dominant or primary team tricode for the player's season slice. |
| `primary_team_name` | `varchar` | Dominant or primary team name for the player's season slice. |
| `is_multi_team_season` | `bigint` | Flag stored as `1` when the player appeared for multiple teams in the slice. |
| `games_on_roster` | `bigint` | Count of game rows where the player appeared on the roster feed. |
| `games_played` | `bigint` | Count of games treated as played by the build rules. |
| `games_started` | `bigint` | Count of games started by the player. |
| `wins` | `bigint` | Count of team wins in the games the player is treated as having played. |
| `losses` | `bigint` | Count of team losses in the games the player is treated as having played. |
| `team_count` | `bigint` | Number of distinct teams the player appeared for in the season slice. |
| `seconds_played_total` | `double` | Total minutes played converted to seconds. |
| `seconds_played_average` | `double` | Average seconds played per game. |
| `minutes_per_game` | `double` | Average minutes played per game, rounded to one decimal place. |
| `points_total` | `bigint` | Total points scored. |
| `assists_total` | `bigint` | Total assists recorded. |
| `rebounds_total` | `bigint` | Total rebounds recorded. |
| `steals_total` | `bigint` | Total steals recorded. |
| `blocks_total` | `bigint` | Total blocks recorded. |
| `turnovers_total` | `bigint` | Total turnovers committed. |
| `double_doubles` | `bigint` | Count of played games in the season slice where the player reached double figures in at least two of points, rebounds, assists, steals, and blocks. |
| `triple_doubles` | `bigint` | Count of played games in the season slice where the player reached double figures in at least three of points, rebounds, assists, steals, and blocks. |
| `quadruple_doubles` | `bigint` | Count of played games in the season slice where the player reached double figures in at least four of points, rebounds, assists, steals, and blocks. |
| `field_goals_percentage` | `double` | Aggregate field goal percentage from total makes and attempts. |
| `three_pointers_percentage` | `double` | Aggregate three-point percentage from total makes and attempts. |
| `free_throws_percentage` | `double` | Aggregate free throw percentage from total makes and attempts. |
| `points_per_game` | `double` | Average points scored per game played. |
| `assists_per_game` | `double` | Average assists recorded per game played. |
| `rebounds_per_game` | `double` | Average rebounds recorded per game played. |
| `rebounds_offensive_total` | `bigint` | Total offensive rebounds recorded. |
| `rebounds_defensive_total` | `bigint` | Total defensive rebounds recorded. |
| `field_goals_made_total` | `bigint` | Total field goals made. |
| `field_goals_attempted_total` | `bigint` | Total field goal attempts. |
| `three_pointers_made_total` | `bigint` | Total three-pointers made. |
| `three_pointers_attempted_total` | `bigint` | Total three-point attempts. |
| `free_throws_made_total` | `bigint` | Total free throws made. |
| `free_throws_attempted_total` | `bigint` | Total free throw attempts. |
| `points_fast_break_total` | `bigint` | Total fast-break points scored. |
| `points_in_the_paint_total` | `bigint` | Total paint points scored. |
| `points_second_chance_total` | `bigint` | Total second-chance points scored. |
| `fouls_offensive_total` | `bigint` | Total offensive fouls committed. |
| `fouls_drawn_total` | `bigint` | Total fouls drawn. |
| `fouls_personal_total` | `bigint` | Total personal fouls committed. |
| `fouls_technical_total` | `bigint` | Total technical fouls committed. |
| `raw_plus_value_total` | `bigint` | Total raw plus values accumulated across games. |
| `raw_minus_value_total` | `bigint` | Total raw minus values accumulated across games. |
| `plus_minus_points_total` | `bigint` | Total on-court point differential across games. |
| `possessions_total` | `double` | Total on-court possessions, equal to offensive plus defensive possessions. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |

## `vw_player_season_provenance_debug`

Grain: one row per `(player_id, season_year, season_type)`.

This Athena-only internal debug view centralizes the provenance and QA fields that were intentionally removed from `agg_player_season` and `vw_player_season_boxscore_advanced`.

| Column | Type | Description |
| --- | --- | --- |
| `player_id` | `bigint` | NBA natural player identifier. |
| `player_name` | `varchar` | Current display name with player name fallback. |
| `season_year` | `varchar` | Season label such as `2024-25`. |
| `season_type` | `varchar` | Canonical season type label such as `regular_season`. |
| `team` | `varchar` | Primary team abbreviation with team-name fallback. |
| `exact_possession_games` | `bigint` | Count of played games in the season slice sourced from exact player possession attribution. |
| `ot_fallback_possession_games` | `bigint` | Count of played games in the season slice sourced from OT fallback possession recovery. |
| `event_estimated_possession_games` | `bigint` | Count of played games in the season slice sourced from event-estimated possession attribution. |
| `boxscore_estimated_possession_games` | `bigint` | Count of played games in the season slice sourced from boxscore minute-share possession fallback. |
| `missing_possession_games` | `bigint` | Count of played games in the season slice with no usable possession attribution. |
| `possession_coverage_pct` | `double` | Covered possession-source games divided by `games_played`, expressed as a percentage. |
| `possession_source_method` | `varchar` | Season-level possession-source label: `exact`, `ot_fallback`, `event_estimated`, `boxscore_estimated`, or `mixed`. |
| `exact_shot_context_games` | `bigint` | Count of played games in the season slice sourced from exact defensive shot-context attribution. |
| `event_estimated_shot_context_games` | `bigint` | Count of played games in the season slice sourced from event-estimated defensive shot-context fallback. |
| `boxscore_estimated_shot_context_games` | `bigint` | Count of played games in the season slice sourced from boxscore minute-share shot-context fallback. |
| `missing_shot_context_games` | `bigint` | Count of played games in the season slice with no usable defensive shot-context attribution. |
| `shot_context_coverage_pct` | `double` | Covered shot-context games divided by `games_played`, expressed as a percentage. |
| `shot_context_source_method` | `varchar` | Season-level shot-context source label: `exact`, `event_estimated`, `boxscore_estimated`, or `mixed`. |
| `offensive_possessions_total` | `double` | Hybrid total offensive possessions while the player was on court. |
| `defensive_possessions_total` | `double` | Hybrid total defensive possessions while the player was on court. |
| `possessions_total` | `double` | Total on-court possessions, equal to offensive plus defensive possessions. |
| `team_points_for_while_on_court_total` | `double` | Hybrid total team points scored while the player was on court. |
| `team_points_against_while_on_court_total` | `double` | Hybrid total opponent points scored while the player was on court. |
| `opponent_two_point_attempts_while_on_court_total` | `double` | Hybrid total opponent two-point attempts while the player was on court. |

## `agg_team_season`

Grain: one row per `(team_id, season_year, raw_season_type_code)`.

| Column | Type | Description |
| --- | --- | --- |
| `agg_team_season_sk` | `bigint` | Surrogate key for the team-season aggregate row. |
| `team_id` | `bigint` | NBA natural team identifier. |
| `current_team_sk` | `bigint` | Current team surrogate key joined for the team. |
| `season_year` | `varchar` | Season label such as `2024-25`. |
| `season_start_year` | `bigint` | Numeric start year for the season label. |
| `raw_season_type_code` | `varchar` | Raw NBA season type code derived from game IDs. |
| `season_type` | `varchar` | Season type label such as `regular_season` or `playoffs`. |
| `games_played` | `bigint` | Total games in the team-season slice. |
| `wins` | `bigint` | Total wins in the slice. |
| `losses` | `bigint` | Total losses in the slice. |
| `ties` | `bigint` | Total ties in the slice. |
| `win_percentage` | `double` | Win percentage for the slice. |
| `home_games` | `bigint` | Total home games in the slice. |
| `away_games` | `bigint` | Total away games in the slice. |
| `home_wins` | `bigint` | Total home wins in the slice. |
| `away_wins` | `bigint` | Total away wins in the slice. |
| `distinct_opponent_count` | `bigint` | Count of distinct opponents faced. |
| `points_for_total` | `bigint` | Total points scored by the team. |
| `points_against_total` | `bigint` | Total points allowed by the team. |
| `point_diff_total` | `bigint` | Total point differential across games. |
| `points_for_per_game` | `double` | Average points scored per game. |
| `points_against_per_game` | `double` | Average points allowed per game. |
| `point_differential_per_game` | `double` | Average point differential per game. |
| `in_bonus_count` | `bigint` | Total bonus-state count accumulated from game rows. |
| `timeouts_remaining_total` | `bigint` | Total timeouts remaining accumulated from game rows. |
| `seconds_played_total` | `double` | Team total minutes in seconds aggregated across the season slice. |
| `seconds_played_average` | `double` | Average team minutes in seconds per game. |
| `assists_total` | `bigint` | Team assists aggregated across the season slice. |
| `blocks_total` | `bigint` | Team blocks aggregated across the season slice. |
| `blocks_received_total` | `bigint` | Team shots blocked against the team across the season slice. |
| `field_goals_attempted_total` | `bigint` | Team field goal attempts aggregated across the season slice. |
| `field_goals_made_total` | `bigint` | Team field goals made aggregated across the season slice. |
| `field_goals_percentage` | `double` | Aggregate team field goal percentage from total makes and attempts. |
| `fouls_offensive_total` | `bigint` | Team offensive fouls aggregated across the season slice. |
| `fouls_drawn_total` | `bigint` | Fouls drawn by the team across the season slice. |
| `fouls_personal_total` | `bigint` | Team personal fouls aggregated across the season slice. |
| `fouls_technical_total` | `bigint` | Team technical fouls aggregated across the season slice. |
| `free_throws_attempted_total` | `bigint` | Team free throw attempts aggregated across the season slice. |
| `free_throws_made_total` | `bigint` | Team free throws made aggregated across the season slice. |
| `free_throws_percentage` | `double` | Aggregate team free throw percentage from total makes and attempts. |
| `rebounds_defensive_total` | `bigint` | Team defensive rebounds aggregated across the season slice. |
| `rebounds_offensive_total` | `bigint` | Team offensive rebounds aggregated across the season slice. |
| `rebounds_total` | `bigint` | Team total rebounds aggregated across the season slice. |
| `steals_total` | `bigint` | Team steals aggregated across the season slice. |
| `turnovers_total` | `bigint` | Team turnovers aggregated across the season slice. |
| `three_pointers_attempted_total` | `bigint` | Team three-point attempts aggregated across the season slice. |
| `three_pointers_made_total` | `bigint` | Team three-pointers made aggregated across the season slice. |
| `three_pointers_percentage` | `double` | Aggregate team three-point percentage from total makes and attempts. |
| `two_pointers_attempted_total` | `bigint` | Team two-point attempts aggregated across the season slice. |
| `two_pointers_made_total` | `bigint` | Team two-pointers made aggregated across the season slice. |
| `two_pointers_percentage` | `double` | Aggregate team two-point percentage from total makes and attempts. |
| `points_fast_break_total` | `bigint` | Team fast-break points aggregated across the season slice. |
| `points_in_the_paint_total` | `bigint` | Team paint points aggregated across the season slice. |
| `points_second_chance_total` | `bigint` | Team second-chance points aggregated across the season slice. |
| `offensive_possessions_total` | `double` | Hybrid total offensive possessions across exact, OT fallback, event-estimated, and boxscore-estimated paths. |
| `defensive_possessions_total` | `double` | Hybrid total defensive possessions across exact, OT fallback, event-estimated, and boxscore-estimated paths. |
| `possessions_total` | `double` | Total team possessions, equal to offensive plus defensive possessions. |
| `opponent_two_point_attempts_total` | `double` | Hybrid total opponent two-point attempts faced by the team across exact, event-estimated, and boxscore-estimated paths. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |

## `team_season_provenance_sidecar`

Grain: one row per `(team_id, season_year, raw_season_type_code)`.

This sidecar is intentionally internal-facing. It keeps provenance and coverage counters separate from the user-facing `agg_team_season` basketball stat surface.

| Column | Type | Description |
| --- | --- | --- |
| `team_season_provenance_sidecar_sk` | `bigint` | Surrogate key for the team-season provenance row. |
| `team_id` | `bigint` | NBA natural team identifier. |
| `current_team_sk` | `bigint` | Current team surrogate key joined for the team. |
| `season_year` | `varchar` | Season label such as `2024-25`. |
| `season_start_year` | `bigint` | Numeric start year for the season label. |
| `raw_season_type_code` | `varchar` | Raw NBA season type code derived from game IDs. |
| `season_type` | `varchar` | Season type label such as `regular_season` or `playoffs`. |
| `exact_possession_games` | `bigint` | Count of team-game rows in the season slice sourced from exact `silver/possessions` attribution. |
| `ot_fallback_possession_games` | `bigint` | Count of team-game rows in the season slice sourced from `silver/possessions_ot_fallback`. |
| `event_estimated_possession_games` | `bigint` | Count of team-game rows in the season slice sourced from event-estimated play-by-play attribution. |
| `boxscore_estimated_possession_games` | `bigint` | Count of team-game rows in the season slice sourced from boxscore-estimated fallback. |
| `missing_possession_games` | `bigint` | Count of team-game rows in the season slice with no usable possession path. |
| `exact_shot_context_games` | `bigint` | Count of team-game rows in the season slice sourced from exact defensive shot-context attribution. |
| `event_estimated_shot_context_games` | `bigint` | Count of team-game rows in the season slice sourced from event-estimated defensive shot-context fallback. |
| `boxscore_estimated_shot_context_games` | `bigint` | Count of team-game rows in the season slice sourced from boxscore opponent-two-point-attempt fallback. |
| `missing_shot_context_games` | `bigint` | Count of team-game rows in the season slice with no usable defensive shot-context path. |
| `record_source` | `varchar` | Source lineage string used to build the row. |
| `created_at_utc` | `timestamp(3)` | UTC timestamp when the row was created in the gold build. |
| `updated_at_utc` | `timestamp(3)` | UTC timestamp when the row was last refreshed in the gold build. |
