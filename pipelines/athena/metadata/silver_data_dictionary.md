# Silver Layer Data Dictionary

This document reflects the current Athena silver surface implemented by the transform scripts under `pipelines/athena/transform/silver/` as of April 12, 2026.

If this file conflicts with the transform scripts, treat the scripts as the implementation source of truth.

Related reference:

- [SILVER_RUNBOOK.md](pipelines/athena/transform/silver/SILVER_RUNBOOK.md)

## Silver Table Inventory

| Table | Grain | Purpose |
| --- | --- | --- |
| `silver/bbr_player_index` | One row per Basketball Reference player id | Driver table parsed from Basketball Reference player index HTML pages. Used to discover canonical player profile URLs. |
| `silver/bbr_player_profile_label_inventory` | One row per detected label occurrence or unlabeled profile paragraph | Discovery table for profiling which labels and paragraph patterns exist across Basketball Reference player profile pages before widening the final profile schema. |
| `silver/bbr_player_profile` | One row per Basketball Reference player id | Flat parsed player-bio table built from Basketball Reference profile HTML. Stable labeled and unlabeled bio fields are normalized into scalar columns. |
| `silver/bbr_player_awards` | One row per Basketball Reference player award occurrence | Structured player honors table parsed from Basketball Reference profile leaderboard sections for official NBA awards, All-Star appearances, and league-team selections. |
| `silver/boxscore_game` | One row per `gameId` | Game-level box score context from the raw CDN box score payload, including timing, status, arena, and attendance fields. |
| `silver/boxscore_game_official` | One row per `(gameId, personId)` | Official assignments extracted from the raw CDN box score payload. |
| `silver/boxscore_player_game` | One row per `(gameId, personId)` | Player box score fact at game grain from the raw CDN box score payload. |
| `silver/boxscore_team_game` | One row per `(gameId, team_side)` | Team box score fact at game grain from the raw CDN box score payload. |
| `silver/boxscore_team_period` | One row per `(gameId, team_side, period_number)` | Team-period scoring breakdown from the raw CDN box score payload. |
| `silver/pbpstats_event_projection_v1` | One row per `(game_id, event_num)` | Standalone pbpstats live/CDN event-semantic sidecar materialized from raw play-by-play JSON. |
| `silver/event_projection_v2` | One row per `(game_id, event_num)` | Raw-first full-contract replacement for `silver/pbpstats_event_projection_v1`, built in parallel from raw play-by-play plus boxscore context without pbpstats loader starter inference. |
| `silver/pbpstats_event_context_v1` | One row per `(game_id, event_num)` | Standalone pbpstats live/CDN event-context sidecar with current-player arrays, lineup ids, and fouls-to-give state. |
| `silver/player_identity_bridge_bbr_nba` | One row per accepted Basketball Reference to NBA player match | Conservative cross-source bridge between Basketball Reference player ids and NBA `person_id` values. |
| `silver/player_identity_bridge_bbr_nba_duplicate_nba` | One row per duplicate NBA-side row that lost a BBR ownership claim | Review output for duplicate NBA-side player records that resolved to an already-claimed Basketball Reference player id but lost to a stronger contender. |
| `silver/player_identity_bridge_bbr_nba_ambiguous` | One row per unresolved NBA player candidate set | Review output for NBA players that produced plausible Basketball Reference candidates but were not auto-matched safely. |
| `silver/player_identity_bridge_bbr_nba_unmatched_nba` | One row per unmatched NBA player | Review output for current NBA players with no Basketball Reference candidate under the current matching rules. |
| `silver/player_identity_bridge_bbr_nba_unmatched_bbr` | One row per unmatched Basketball Reference player | Review output for Basketball Reference players not linked to the current NBA-side population under the current matching rules. |
| `silver/player_movement` | One row per player movement transaction in the chosen snapshot | Flat player movement snapshot from the raw CDN player movement export. |
| `silver/players` | One row per Kaggle player row | Legacy Kaggle player master table retained as a silver reference artifact. |
| `silver/playbyplay` | One row per source action | Canonical event-grain play-by-play table. Preserves source columns and adds semantic basketball context. |
| `silver/on_court_state` | One row per lineup stint | Tracks the active home and away 5-man units across substitution boundaries. |
| `silver/possessions` | One row per possession | Materializes possession spans, possession context, and lineup context at possession grain. |
| `silver/possessions_ot_fallback` | One row per recovered fallback possession | Separate possession artifact for recoverable overtime games where the pbpstats-exact loader failed. |
| `silver/player_game_possession_context` | One row per `(game_id, person_id)` | Canonical player-game on-court possession attribution table that blends exact possessions, OT fallback possessions, event-estimated recovery, and boxscore minute-share fallback with explicit provenance flags. |
| `silver/player_game_defensive_shot_context` | One row per `(game_id, person_id)` | Canonical player-game defensive shot attribution table for opponent two-point attempts while the player is on court, with exact on-court, event-estimated, and boxscore fallback provenance. |
| `silver/player_game_opportunity_context` | One row per `(game_id, person_id)` | Canonical player-game opportunity attribution table for teammate made field goals and rebound opportunities while the player is on court, with separate assist-family and rebound-family provenance. |
| `silver/team_game_possession_context` | One row per `(game_id, team_id)` | Canonical team-game possession attribution table that blends exact possessions, OT fallback possessions, event-estimated recovery, and boxscore-estimated fallback with explicit provenance flags. |
| `silver/scheduleLeagueV2_1` | One row per scheduled game | Flat schedule table from the raw CDN `scheduleLeagueV2_1` payload. |
| `silver/team_histories` | One row per Kaggle team-history row | Legacy Kaggle team-history reference table. |

## General Notes

- `silver/playbyplay` is additive over the live NBA JSON. It intentionally keeps many source-shaped columns while also adding derived semantic fields.
- `silver/pbpstats_event_projection_v1` and `silver/pbpstats_event_context_v1` are the current Athena pbpstats sidecars built directly from the live/CDN source family.
- `silver/event_projection_v2` is the raw-first projection table that targets the same 120-column stable contract as `silver/pbpstats_event_projection_v1` while avoiding pbpstats enhanced-loader starter inference.
- `silver/on_court_state` and `silver/possessions` are separate because they are different grains from the source action stream.
- `silver/possessions_ot_fallback` is intentionally separate from `silver/possessions`; it should be treated as a recovery ledger, not as pbpstats-exact output.
- `silver/player_game_possession_context` is the canonical silver serving layer for player on-court possessions and on-court points. Gold season attribution should sum this table rather than restitch possession sidecars directly.
- `silver/player_game_possession_context` also carries the canonical player-game used-possession numerator for higher-quality downstream usage rate calculations.
- `silver/player_game_defensive_shot_context` is the canonical silver serving layer for player on-court opponent two-point-attempt attribution. Gold block-rate denominators should sum this table rather than re-estimate opponent 2PA from team season context.
- `silver/player_game_opportunity_context` is the canonical silver serving layer for player on-court assist and rebound opportunity denominators. Gold season attribution should sum this table rather than rely on minute-share proxy formulas for AST% and rebound percentages.
- `silver/team_game_possession_context` is the canonical silver serving layer for team-game possessions. Gold team-season possession totals should sum this table rather than re-estimate possessions inside the serving view.
- The Basketball Reference silver tables are sourced from raw HTML snapshots, not JSON APIs. Schema discovery therefore relies on label inventorying and paragraph-shape parsing rather than fixed response contracts.
- `silver/player_identity_bridge_bbr_nba` is intentionally conservative and should be treated as an iterative matching artifact rather than a final canonical dimension. The matched table is now ownership-resolved so each Basketball Reference id appears at most once. Ambiguous, duplicate-NBA, and unmatched outputs are part of the expected workflow.
- Some Phase 6 period-start logic supports optional override metadata via [playbyplay_period_start_overrides.json](pipelines/athena/metadata/playbyplay_period_start_overrides.json).

## Additional Current Athena Silver Tables

The sections below go deepest on the Basketball Reference tables plus the canonical event / lineup / possession layer. The following tables are also part of the current supported Athena silver surface and should be treated as current implementation, even though they are documented more compactly here.

### `silver/boxscore_game`

Grain: one row per `gameId`.

Source:
- `raw/cdn/boxscore/`

Core columns:
- `meta_version`, `meta_code`, `meta_request`, `meta_time`
- `gameId`, `gameCode`
- `gameTimeLocal`, `gameTimeUTC`, `gameTimeHome`, `gameTimeAway`, `gameEt`
- `duration`, `gameStatus`, `gameStatusText`, `regulationPeriods`, `period`, `gameClock`
- `attendance`, `sellout`
- `arenaId`, `arenaName`, `arenaCity`, `arenaState`, `arenaCountry`, `arenaTimezone`

### `silver/boxscore_game_official`

Grain: one row per `(gameId, personId)`.

Source:
- `raw/cdn/boxscore/`

Core columns:
- `gameId`, `personId`
- `name`, `nameI`, `firstName`, `familyName`
- `jerseyNum`, `assignment`

### `silver/boxscore_player_game`

Grain: one row per `(gameId, personId)`.

Source:
- `raw/cdn/boxscore/`

Core columns:
- identity / participation:
  - `gameId`, `teamId`, `team_side`, `personId`, `name`, `nameI`, `jerseyNum`, `position`
  - `status`, `order`, `starter`, `oncourt`, `played`
- time and plus/minus:
  - `minutes`, `minutesCalculated`, `plus`, `minus`, `plusMinusPoints`
- box score totals:
  - `points`, `assists`, `reboundsTotal`, `reboundsOffensive`, `reboundsDefensive`, `steals`, `blocks`, `turnovers`
- shooting and fouls:
  - `fieldGoalsMade`, `fieldGoalsAttempted`, `threePointersMade`, `threePointersAttempted`
  - `twoPointersMade`, `twoPointersAttempted`, `freeThrowsMade`, `freeThrowsAttempted`
  - `foulsOffensive`, `foulsDrawn`, `foulsPersonal`, `foulsTechnical`
- efficiencies:
  - `fieldGoalsPercentage`, `threePointersPercentage`, `twoPointersPercentage`, `freeThrowsPercentage`

### `silver/boxscore_team_game`

Grain: one row per `(gameId, team_side)`.

Source:
- `raw/cdn/boxscore/`

Core columns:
- identity:
  - `gameId`, `team_side`, `teamId`, `teamName`, `teamCity`, `teamTricode`
- scoreboard / context:
  - `score`, `pointsAgainst`, `inBonus`, `timeoutsRemaining`, `leadChanges`, `timesTied`, `biggestLead`, `biggestScoringRun`
- team totals:
  - `points`, `assists`, `steals`, `turnovers`, `blocks`
  - `reboundsTotal`, `reboundsOffensive`, `reboundsDefensive`, `reboundsTeam`, `reboundsTeamOffensive`, `reboundsTeamDefensive`
  - `fieldGoalsMade`, `fieldGoalsAttempted`, `threePointersMade`, `threePointersAttempted`
  - `twoPointersMade`, `twoPointersAttempted`, `freeThrowsMade`, `freeThrowsAttempted`
- shooting / rate helpers:
  - `fieldGoalsPercentage`, `threePointersPercentage`, `freeThrowsPercentage`, `fieldGoalsEffectiveAdjusted`, `assistsTurnoverRatio`

### `silver/boxscore_team_period`

Grain: one row per `(gameId, team_side, period_number)`.

Source:
- `raw/cdn/boxscore/`

Core columns:
- `gameId`, `teamId`, `team_side`
- `period_number`, `periodType`, `period_score`

### `silver/pbpstats_event_projection_v1`

Grain: one row per `(game_id, event_num)`.

Source:
- `raw/cdn/playbyplay/`

Core columns:
- identity / ordering:
  - `game_id`, `event_num`, `order`, `period`, `clock`, `seconds_remaining_in_period`
- event semantics:
  - `action_type`, `sub_type`, `description`, `team_id`, `player1_id`, `player2_id`, `player3_id`
  - `offense_team_id`, `defense_team_id`
- possession semantics:
  - `is_possession_ending_event`, `count_as_possession`, `possession_boundary_reason`
  - `is_second_chance_event`, `is_penalty_event`
- event-family flags and links:
  - `is_made_shot`, `is_missed_shot`, `is_free_throw`, `is_rebound`, `is_turnover`, `is_substitution`, `is_timeout`, `is_jump_ball`
  - linked-action numbers and pbpstats-derived context fields

### `silver/event_projection_v2`

Grain: one row per `(game_id, event_num)`.

Source:
- `raw/cdn/playbyplay/`
- `raw/cdn/boxscore/` or CDN boxscore fallback when the raw boxscore object is missing

Core columns:
- same 120-column stable projection contract and column order as `silver/pbpstats_event_projection_v1`
- identity / ordering:
  - `game_id`, `event_num`, `event_order`, `period`, `clock`
- event semantics:
  - `action_type`, `sub_type`, `descriptor`, `description`, `team_id`, `player1_id`, `player2_id`, `player3_id`
  - `offense_team_id`, `home_score`, `away_score`, `shot_action_number`, `qualifiers`, `loc_x_legacy`, `loc_y_legacy`
- derived context:
  - `seconds_remaining`, `seconds_since_previous_event`, `score_margin`
  - `is_possession_ending_event`, `count_as_possession`, `is_second_chance_event`, `is_penalty_event`
- linked references and event families:
  - `previous_event_num`, `next_event_num`, `missed_shot_event_num`, `foul_that_led_to_ft_event_num`
  - the full field-goal / free-throw / rebound / foul / turnover / violation / replay / period column set from the shared 120-column projection contract

Implementation notes:
- `silver/event_projection_v2` is raw-first and does not use `LiveEnhancedPbpLoader`, `period_starters`, `current_players`, or `silver/pbpstats_event_context_v1` at runtime.
- `silver/on_court_state` now consumes `silver/event_projection_v2` as its runtime event source.

### `silver/pbpstats_event_context_v1`

Grain: one row per `(game_id, event_num)`.

Source:
- `raw/cdn/playbyplay/`

Columns:
- `game_id`, `event_num`
- `home_team_id`, `away_team_id`
- `home_current_player_ids`, `away_current_player_ids`
- `home_lineup_id`, `away_lineup_id`
- `home_fouls_to_give`, `away_fouls_to_give`
- `home_period_starter_ids`, `away_period_starter_ids`

### `silver/player_movement`

Grain: one row per player movement transaction in the selected snapshot.

Source:
- `raw/cdn/player_movement/snapshot_date=YYYY-MM-DD/player_movement.json`

Columns:
- `Transaction_Type`, `TRANSACTION_DATE`, `TRANSACTION_DESCRIPTION`
- `TEAM_ID`, `TEAM_SLUG`
- `PLAYER_ID`, `PLAYER_SLUG`
- `Additional_Sort`, `GroupSort`

### `silver/players`

Grain: one row per raw Kaggle player record.

Source:
- `raw/kaggle/Players.csv`

Columns:
- the table keeps the source Kaggle player columns from `Players.csv`
- plus standard silver metadata columns

### `silver/possessions_ot_fallback`

Grain: one row per recovered fallback possession.

Source:
- `raw/cdn/playbyplay/`
- `silver/on_court_state`
- pbpstats-exact possession path attempted first, then narrow OT-only fallback families

Columns:
- all core `silver/possessions` columns
- plus fallback provenance:
  - `possessionSourceMethod`
  - `referenceFailureType`
  - `referenceFailurePeriod`
  - `fallbackApplied`
  - `fallbackOpeningSubClusterApplied`

### `silver/player_game_possession_context`

Grain: one row per `(game_id, person_id)`.

Source:
- `silver/boxscore_player_game`
- `silver/boxscore_team_game`
- `silver/scheduleLeagueV2_1`
- `silver/possessions`
- `silver/possessions_ot_fallback`
- `silver/on_court_state`
- `silver/playbyplay`

Core columns:
- identity:
  - `game_id`, `person_id`, `team_id`, `season_year`, `season_start_year`, `season_type_code`, `season_type`
- canonical on-court totals:
  - `offensive_possessions`, `defensive_possessions`, `possessions_total`
  - `used_offensive_possessions`
  - `team_points_for_while_on_court`, `team_points_against_while_on_court`
- provenance counts:
  - `exact_possessions_count`, `recovered_from_on_court_count`, `ot_fallback_possessions_count`
  - `event_estimated_possessions_count`, `boxscore_estimated_possessions_count`, `missing_possessions_count`
- game-level provenance flags:
  - `exact_game_flag`, `ot_fallback_game_flag`, `event_estimated_game_flag`
  - `boxscore_estimated_game_flag`, `missing_game_flag`
- method tag:
  - `possession_source_method`

### `silver/player_game_defensive_shot_context`

Grain: one row per `(game_id, person_id)`.

Source:
- `silver/boxscore_player_game`
- `silver/boxscore_team_game`
- `silver/scheduleLeagueV2_1`
- `silver/playbyplay`
- `silver/on_court_state`
- `silver/pbpstats_event_context_v1`

Core columns:
- identity:
  - `game_id`, `person_id`, `team_id`, `season_year`, `season_start_year`, `season_type_code`, `season_type`
- canonical defensive shot total:
  - `opponent_two_point_attempts_while_on_court`
- provenance counts:
  - `exact_two_point_attempts_count`, `event_estimated_two_point_attempts_count`
  - `boxscore_estimated_two_point_attempts_count`, `missing_two_point_attempts_count`
- game-level provenance flags:
  - `exact_game_flag`, `event_estimated_game_flag`
  - `boxscore_estimated_game_flag`, `missing_game_flag`
- method tag:
  - `shot_context_source_method`

### `silver/player_game_opportunity_context`

Grain: one row per `(game_id, person_id)`.

Source:
- `silver/boxscore_player_game`
- `silver/boxscore_team_game`
- `silver/scheduleLeagueV2_1`
- `silver/playbyplay`
- `silver/on_court_state`
- `silver/pbpstats_event_context_v1`

Core columns:
- identity:
  - `game_id`, `person_id`, `team_id`, `season_year`, `season_start_year`, `season_type_code`, `season_type`
- canonical opportunity totals:
  - `teammate_field_goals_made_while_on_court`
  - `offensive_rebound_opportunities_while_on_court`
  - `defensive_rebound_opportunities_while_on_court`
  - `rebound_opportunities_while_on_court`
- assist-family provenance:
  - `assist_context_source_method`
  - `assist_exact_count`, `assist_event_estimated_count`
  - `assist_boxscore_estimated_count`, `assist_missing_count`
  - `assist_exact_game_flag`, `assist_event_estimated_game_flag`
  - `assist_boxscore_estimated_game_flag`, `assist_missing_game_flag`
- rebound-family provenance:
  - `rebound_context_source_method`
  - `rebound_exact_count`, `rebound_event_estimated_count`
  - `rebound_boxscore_estimated_count`, `rebound_missing_count`
  - `rebound_exact_game_flag`, `rebound_event_estimated_game_flag`
  - `rebound_boxscore_estimated_game_flag`, `rebound_missing_game_flag`

### `silver/team_game_possession_context`

Grain: one row per `(game_id, team_id)`.

Source:
- `silver/boxscore_team_game`
- `silver/scheduleLeagueV2_1`
- `silver/possessions`
- `silver/possessions_ot_fallback`
- `silver/playbyplay`

Core columns:
- identity:
  - `game_id`, `team_id`, `season_year`, `season_start_year`, `season_type_code`, `season_type`
- canonical team possession totals:
  - `offensive_possessions`, `defensive_possessions`, `possessions_total`
- provenance counts:
  - `exact_possessions_count`, `ot_fallback_possessions_count`
  - `event_estimated_possessions_count`, `boxscore_estimated_possessions_count`, `missing_possessions_count`
- game-level provenance flags:
  - `exact_game_flag`, `ot_fallback_game_flag`, `event_estimated_game_flag`
  - `boxscore_estimated_game_flag`, `missing_game_flag`
- method tag:
  - `possession_source_method`

### `silver/scheduleLeagueV2_1`

Grain: one row per scheduled game.

Source:
- `raw/cdn/scheduleLeagueV2_1.json`

Core columns:
- season / identity:
  - `seasonYear`, `leagueId`, `gameId`, `gameCode`, `gameSequence`
- timing:
  - `gameDate`, `gameDateTimeUTC`, `day`, `monthNum`, `weekNumber`, `weekName`
- status / labeling:
  - `gameStatus`, `gameStatusText`, `postponedStatus`, `ifNecessary`
  - `gameLabel`, `gameSubLabel`, `gameSubtype`, `seriesGameNumber`, `seriesText`
- arena / matchup:
  - `isNeutral`, `arenaName`, `arenaCity`, `arenaState`
  - `homeTeamId`, `homeTeamName`, `homeTeamCity`, `homeTeamTricode`, `homeTeamSlug`
  - `awayTeamId`, `awayTeamName`, `awayTeamCity`, `awayTeamTricode`, `awayTeamSlug`

### `silver/team_histories`

Grain: one row per raw Kaggle team-history record.

Source:
- `raw/kaggle/TeamHistories.csv`

Columns:
- the table keeps the source Kaggle team-history columns from `TeamHistories.csv`
- plus standard silver metadata columns

## Basketball Reference Silver Tables

### `silver/bbr_player_index`

Grain: one row per `basketball_reference_player_id`.

Design notes:

- Parsed from raw Basketball Reference letter index pages under `raw/bball-reference/players_index/`.
- Used as the canonical driver table for profile scraping. Downstream profile ingestion should rely on `player_profile_url`, not reconstructed URLs.
- Includes basic index-page fields only. It is not the full player-bio dimension table.

Representative columns:

| Column | Type | Description |
| --- | --- | --- |
| `basketball_reference_player_id` | `string` | Canonical Basketball Reference player id such as `abdulka01`. |
| `player_name` | `string` | Displayed player name from the index page. |
| `player_profile_url` | `string` | Canonical Basketball Reference player profile URL. |
| `letter` | `string` | Letter page where the player was discovered. This is discovery lineage, not a guaranteed canonical URL partition. |
| `year_min` | `int64` | First season year shown on the index page. |
| `year_max` | `int64` | Last season year shown on the index page. |
| `position` | `string` | Index-page position text. |
| `height_inches` | `int64` | Height converted from the index-page height string. |
| `weight_lbs` | `int64` | Weight in pounds from the index page. |
| `birth_date` | `date32` | Birth date derived from the index-page birth row when present. |
| `colleges_raw` | `string` | Pipe-delimited college string from the index page when multiple colleges appear. |
| `hall_of_fame_flag` | `int64` | `1` when the index row carries the Hall of Fame marker. |

### `silver/bbr_player_profile_label_inventory`

Grain: one row per detected label occurrence, or one row per unlabeled paragraph when no label was detected in that paragraph.

Design notes:

- This table exists for schema discovery and parser refinement.
- Useful facts can still appear in unlabeled paragraphs, including full names, nicknames, former-name notes, and measurement lines.
- The table should be used to determine which profile facts are stable enough to promote into first-class columns.

Representative columns:

| Column | Type | Description |
| --- | --- | --- |
| `basketball_reference_player_id` | `string` | Basketball Reference player id. |
| `page_player_name` | `string` | Rendered page heading name from the profile. |
| `paragraph_index` | `int64` | Paragraph order within the profile `div#meta` block. |
| `paragraph_html_raw` | `string` | Raw paragraph HTML captured for label review. |
| `paragraph_text_raw` | `string` | Tag-stripped paragraph text. |
| `has_detected_label` | `int64` | `1` when one or more labels were detected in the paragraph, else `0`. |
| `label_text_raw` | `string` | Raw label text when detected. |
| `label_name_normalized` | `string` | Normalized label token used for frequency analysis. |

### `silver/bbr_player_profile`

Grain: one row per `basketball_reference_player_id`.

Design notes:

- Built from the latest raw profile HTML snapshot per Basketball Reference player.
- Stable labeled facts and common unlabeled paragraph patterns are flattened into scalar columns.
- Multi-value concepts remain flat strings rather than nested arrays or JSON blobs.
- Nullability is expected because not every profile page contains every bio field.

Representative columns:

| Column | Type | Description |
| --- | --- | --- |
| `basketball_reference_player_id` | `string` | Basketball Reference player id. |
| `player_profile_url` | `string` | Canonical player profile URL. |
| `page_player_name` | `string` | Rendered profile heading name. |
| `formal_name` | `string` | Alternate or formal name parsed from unlabeled bio paragraphs when present. |
| `pronunciation` | `string` | Pronunciation text from the profile when present. |
| `former_name_note` | `string` | Former-name or name-change note parsed from unlabeled paragraphs. |
| `nicknames_raw` | `string` | Flat nickname string from nickname paragraphs. |
| `instagram_handle` | `string` | Instagram handle when present in the formal-name line. |
| `position_raw` | `string` | Profile position text. |
| `shoots` | `string` | Shooting hand. |
| `height_inches` | `int64` | Height converted to inches. |
| `weight_lbs` | `int64` | Weight in pounds. |
| `current_team_raw` | `string` | Current team text when Basketball Reference shows an active team line. |
| `birth_date` | `date32` | Birth date parsed from the profile. |
| `birth_place_raw` | `string` | Flat birthplace string from the profile. |
| `birth_country_code` | `string` | Two-letter birthplace country badge when present. |
| `death_date` | `date32` | Death date when present on historical profiles. |
| `college_raw` | `string` | Single-college field from the profile. |
| `colleges_raw` | `string` | Multi-college flat string from the profile. |
| `high_school_raw` | `string` | Single high-school field from the profile. |
| `high_schools_raw` | `string` | Multi-high-school flat string from the profile. |
| `recruiting_rank_year` | `int64` | Recruiting class year when the profile includes a recruiting-rank field. |
| `recruiting_rank_ordinal` | `int64` | Recruiting rank ordinal when present. |
| `relatives_raw` | `string` | Relatives field text when present. |
| `draft_team_raw` | `string` | Drafting team text parsed from the draft field. |
| `draft_year` | `int64` | Draft year parsed from the profile. |
| `draft_round` | `int64` | Draft round parsed from the profile. |
| `draft_pick_overall` | `int64` | Overall draft pick parsed from the profile when present. |
| `draft_selection_note` | `string` | Draft note such as `territorial selection` when present. |
| `nba_debut_date` | `date32` | NBA debut date when present. |
| `aba_debut_date` | `date32` | ABA debut date when present. |
| `experience_years` | `int64` | Experience value from active-player profiles when present. |
| `career_length_years` | `int64` | Career length value from historical-player profiles when present. |
| `hall_of_fame_flag` | `int64` | `1` when the profile includes a Hall of Fame field. |
| `hall_of_fame_role` | `string` | Hall of Fame induction role when present. |
| `hall_of_fame_year` | `int64` | Hall of Fame induction year when present. |

### `silver/bbr_player_awards`

Grain: one row per Basketball Reference player award occurrence.

Design notes:

- Built from the latest raw profile HTML snapshot per Basketball Reference player.
- This table intentionally keeps a separate one-to-many grain rather than widening `silver/bbr_player_profile`.
- Current scope is the curated awards family set parsed from the `leaderboard_notable-awards`, `leaderboard_allstar`, and `leaderboard_all_league` sections.
- `award_family` is normalized for querying, while `award_label_raw` preserves the original Basketball Reference display text.

Representative columns:

| Column | Type | Description |
| --- | --- | --- |
| `basketball_reference_player_id` | `string` | Basketball Reference player id. |
| `player_profile_url` | `string` | Canonical player profile URL. |
| `page_player_name` | `string` | Rendered profile heading name. |
| `source_section` | `string` | Source leaderboard section such as `notable_awards`, `all_star`, or `all_league`. |
| `award_family` | `string` | Normalized award family such as `mvp`, `finals_mvp`, `dpoy`, `sixth_man`, `mip`, `roy`, `all_star`, `all_nba`, `all_defensive`, or `all_rookie`. |
| `league_code` | `string` | League code parsed from the source entry when present, such as `NBA` or `ABA`. |
| `season_label` | `string` | Canonical season label for the award occurrence, such as `2021-22`. |
| `team_tier` | `int64` | Team tier for league-team honors when present, such as `1`, `2`, or `3`. |
| `award_label_raw` | `string` | Original Basketball Reference award text for the occurrence. |
| `award_reference_url` | `string` | Relative Basketball Reference href attached to the source occurrence. |

### `silver/player_identity_bridge_bbr_nba`

Grain: one row per accepted Basketball Reference to NBA player match.

Design notes:

- This bridge links `basketball_reference_player_id` to NBA `person_id`.
- Current scope is the current NBA-side player population from gold `dim_player`.
- Matching starts from normalized exact-name candidates and then applies conservative confirmation logic.
- Draft alignment is the strongest confirmation signal when present.
- Weight, school, and position are supporting signals only.
- Era sanity checks prevent clearly impossible cross-era auto-links.

Representative columns:

| Column | Type | Description |
| --- | --- | --- |
| `nba_person_id` | `int64` | NBA player id from the gold current-player population. |
| `nba_player_name` | `string` | NBA-side display name used in the bridge. |
| `basketball_reference_player_id` | `string` | Accepted Basketball Reference player id. |
| `bbr_player_name` | `string` | Basketball Reference display name. |
| `match_method` | `string` | Acceptance reason such as unique normalized name or draft-supported top candidate. |
| `match_confidence` | `double` | Current heuristic confidence score for the accepted match. |
| `name_key` | `string` | Normalized name token used for candidate generation. |
| `draft_match_flag` | `int64` | `1` when draft year, round, and overall pick align across sources. |
| `weight_match_flag` | `int64` | `1` when weights align closely across sources. |
| `school_match_flag` | `int64` | `1` when normalized school strings align or materially overlap. |
| `position_match_flag` | `int64` | `1` when source position tokens overlap. |
| `era_sanity_flag` | `int64` | `1` when Basketball Reference career timing is plausible for the NBA-side observation window. |

### `silver/player_identity_bridge_bbr_nba_ambiguous`

Grain: one row per unresolved NBA player candidate set.

Design notes:

- Holds NBA players that produced one or more plausible Basketball Reference candidates but failed conservative auto-acceptance.
- `candidate_reasons` stores compact score/evidence summaries for manual review.

### `silver/player_identity_bridge_bbr_nba_duplicate_nba`

Grain: one row per duplicate NBA-side player row that lost ownership of a Basketball Reference id.

Design notes:

- This table captures NBA-side duplicate-source rows that resolved to an already-claimed `basketball_reference_player_id`.
- The matched bridge keeps only the strongest NBA-side owner for each BBR id; non-winning contenders are written here instead of silently duplicating the bridge.
- `duplicate_reason` currently records ownership losses as `bbr_id_claimed_by_stronger_nba_row`.

Representative columns:

| Column | Type | Description |
| --- | --- | --- |
| `nba_person_id` | `int64` | NBA-side duplicate player row that lost the ownership claim. |
| `nba_player_name` | `string` | NBA-side display name for the losing row. |
| `basketball_reference_player_id` | `string` | BBR id both rows attempted to claim. |
| `candidate_match_method` | `string` | Match method the losing row would have used absent the ownership collision. |
| `candidate_match_score` | `int64` | Match score for the losing row against the claimed BBR id. |
| `winning_nba_person_id` | `int64` | NBA-side row that won ownership of the BBR id. |
| `winning_match_method` | `string` | Match method used by the winning row. |
| `winning_match_score` | `int64` | Match score for the winning row. |
| `duplicate_reason` | `string` | Duplicate ownership classification. |

### `silver/player_identity_bridge_bbr_nba_unmatched_nba`

Grain: one row per current NBA player with no Basketball Reference candidate under the current matching rules.

Design notes:

- Useful for identifying missing name normalizations, sparse source coverage, or modern players not yet represented cleanly in the current bridge logic.

### `silver/player_identity_bridge_bbr_nba_unmatched_bbr`

Grain: one row per Basketball Reference player not linked to the current NBA-side player population under the current matching rules.

Design notes:

- Expected to be large because the Basketball Reference source covers much more history than the current NBA-side warehouse population.
- Useful for spotting modern players who should have matched but did not.

## `silver/playbyplay`

Grain: one row per source action from the live play-by-play feed.

### Design Notes

- Source lineage is preserved through fields like `actionType`, `subType`, `personId`, `teamId`, `scoreHome`, `scoreAway`, `shotActionNumber`, and `qualifiers`.
- Semantic fields such as `resolvedOffenseTeamId`, `isPossessionEndingEvent`, `isSecondChanceEvent`, and `teamStartingPeriodWithBall` are derived in silver for downstream usability.
- `scoreMarginBefore` and `scoreMarginAfter` are oriented from the perspective of the resolved offense team, not always from the home-team perspective.
- Standard silver lineage fields `_meta_pipeline_run_id`, `_meta_ingested_at_utc`, `_meta_source_system`, `_meta_source_key`, `_meta_source_last_modified_utc`, and `_meta_schema_version` are appended at write time.

| Column | Type | Description |
| --- | --- | --- |
| `gameId` | `string` | NBA natural game identifier. |
| `gameDateTimeEst` | `string` | Game datetime string from boxscore context in Eastern Time representation. |
| `actionNumber` | `int64` | Source event number within the game feed. |
| `actionType` | `string` | Source event action type. |
| `prevActionNumber` | `int64` | Previous action number in the same game period after silver ordering. |
| `nextActionNumber` | `int64` | Next action number in the same game period after silver ordering. |
| `area` | `string` | Source area label when present. |
| `areaDetail` | `string` | Source area detail label when present. |
| `assistPersonId` | `int64` | Source assisting player id. |
| `assistFullName` | `string` | Derived full name for `assistPersonId`. |
| `assistPlayerName` | `string` | Source assisting player short name. |
| `assistPlayerNameInitial` | `string` | Source assisting player initial-style name. |
| `assistTotal` | `int64` | Source cumulative assist total for the player on this event. |
| `blockPersonId` | `int64` | Source blocking player id. |
| `blockFullName` | `string` | Derived full name for `blockPersonId`. |
| `blockPlayerName` | `string` | Source blocking player short name. |
| `clock` | `string` | Source ISO-style period clock string. |
| `description` | `string` | Source event description text. |
| `descriptor` | `string` | Source event descriptor used for foul and free-throw semantics. |
| `edited` | `string` | Source edited timestamp or marker when present. |
| `foulDrawnPersonId` | `int64` | Source player id for the fouled player. |
| `foulDrawnFullName` | `string` | Derived full name for `foulDrawnPersonId`. |
| `foulDrawnPlayerName` | `string` | Source fouled player short name. |
| `foulPersonalTotal` | `int64` | Source cumulative personal foul total for the player on this event. |
| `foulTechnicalTotal` | `int64` | Source cumulative technical foul total for the player on this event. |
| `isFieldGoal` | `int64` | Source field-goal flag as delivered by the feed. |
| `isTargetScoreLastPeriod` | `bool` | Source target-score marker for Elam-style periods when present. |
| `jerseyNumber` | `string` | Source jersey number. |
| `location` | `string` | Derived team side for `teamId`, usually `h` or `v`. |
| `jumpBallLostFullName` | `string` | Derived full name for `jumpBallLostPersonId`. |
| `jumpBallLostPersonId` | `int64` | Source player id for jump-ball loser. |
| `jumpBallLostPlayerName` | `string` | Source jump-ball loser name. |
| `jumpBallRecoveredFullName` | `string` | Derived full name for jump-ball recovery player id. |
| `jumpBallRecoveredName` | `string` | Source jump-ball recovery player name. |
| `jumpBallRecoveredPersonId` | `int64` | Canonicalized jump-ball recovery player id, including typo repair from the feed. |
| `jumpBallWonFullName` | `string` | Derived full name for `jumpBallWonPersonId`. |
| `jumpBallWonPersonId` | `int64` | Source player id for jump-ball winner. |
| `jumpBallWonPlayerName` | `string` | Source jump-ball winner name. |
| `officialId` | `int64` | Source official id when attached to the event. |
| `orderNumber` | `int64` | Source event ordering number used for stable event sequencing. |
| `prevOrderNumber` | `int64` | Previous `orderNumber` in the same game period after silver ordering. |
| `nextOrderNumber` | `int64` | Next `orderNumber` in the same game period after silver ordering. |
| `period` | `int64` | Period number. |
| `periodType` | `string` | Period type label from the source feed. |
| `personId` | `int64` | Primary player id attached to the event. |
| `personIdsFilter` | `list<int64>` | Source list of person ids attached to the event filter payload. |
| `playerFullName` | `string` | Derived full name for `personId`. |
| `playerName` | `string` | Source player short name. |
| `playerNameI` | `string` | Source player initial-style name. |
| `playerteamCity` | `string` | Derived city name for `teamId`. |
| `playerteamName` | `string` | Derived team name for `teamId`. |
| `pointsTotal` | `int64` | Source cumulative points total for the player on this event. |
| `opponentteamCity` | `string` | Derived opponent city for `teamId`. |
| `opponentteamName` | `string` | Derived opponent team name for `teamId`. |
| `possession` | `int64` | Source possession team id from the feed. Preserved for lineage. |
| `qualifiers` | `list<string>` | Source qualifier list used in rebound and foul semantics. |
| `reboundDefensiveTotal` | `int64` | Source cumulative defensive rebounds total. |
| `reboundOffensiveTotal` | `int64` | Source cumulative offensive rebounds total. |
| `reboundTotal` | `int64` | Source cumulative rebounds total. |
| `scoreAway` | `int64` | Source away score after the event. |
| `scoreHome` | `int64` | Source home score after the event. |
| `scoreMarginBefore` | `int64` | Derived score margin before the event from the offense team's perspective. |
| `scoreMarginAfter` | `int64` | Derived score margin after the event from the offense team's perspective. |
| `shortFormattedClock` | `string` | Source short clock string when present. |
| `shotActionNumber` | `int64` | Source shot-linked action number, mainly used on rebound rows. |
| `shotDistance` | `double` | Source shot distance. |
| `shotResult` | `string` | Source shot result text. |
| `shotValue` | `int64` | Derived shot point value. |
| `side` | `string` | Source side label when present. |
| `resolvedOffenseTeamId` | `int64` | Derived offense team id after silver repairs and period-start inference. |
| `resolvedDefenseTeamId` | `int64` | Derived defense team id paired with `resolvedOffenseTeamId`. |
| `offenseHomeAway` | `string` | Derived side label for the offense team. |
| `defenseHomeAway` | `string` | Derived side label for the defense team. |
| `secondsRemainingInPeriod` | `double` | Derived seconds remaining in the period from `clock`. |
| `secondsSincePreviousEvent` | `double` | Derived elapsed seconds since the previous same-period event. |
| `stealPersonId` | `int64` | Source stealing player id. |
| `stealFullName` | `string` | Derived full name for `stealPersonId`. |
| `stealPlayerName` | `string` | Source stealing player name. |
| `stealTotal` | `int64` | Source cumulative steals total for the player on this event. |
| `subType` | `string` | Source subtype string used heavily in semantic classification. |
| `subsInFullName` | `string` | Derived incoming player full name for substitution text parsing. |
| `subsInPersonId` | `int64` | Derived incoming player id for substitution text parsing. |
| `subsInPlayerName` | `string` | Derived incoming player short name for substitution text parsing. |
| `teamId` | `int64` | Source team id attached to the event. |
| `teamTricode` | `string` | Source team tricode. |
| `timeActual` | `string` | Source wall-clock timestamp for the event. |
| `turnoverTotal` | `int64` | Source cumulative turnover total for the player on this event. |
| `value` | `string` | Source generic value field when present. |
| `x` | `double` | Source shot or event x-coordinate. |
| `xLegacy` | `double` | Source legacy x-coordinate. |
| `y` | `double` | Source shot or event y-coordinate. |
| `yLegacy` | `double` | Source legacy y-coordinate. |
| `isMadeShot` | `bool` | Derived flag for made field goals only. |
| `isMissedShot` | `bool` | Derived flag for missed field goals only. |
| `isFreeThrow` | `bool` | Derived flag for free-throw events. |
| `isRebound` | `bool` | Derived flag for rebound events. |
| `isTurnover` | `bool` | Derived flag for turnover events. |
| `isFoul` | `bool` | Derived flag for foul events. |
| `isSubstitution` | `bool` | Derived flag for substitution events. |
| `isTimeout` | `bool` | Derived flag for timeout events. |
| `isJumpBall` | `bool` | Derived flag for jump-ball events. |
| `isPossessionEndingEvent` | `bool` | Derived flag for events that end a possession boundary. |
| `countAsPossession` | `bool` | Derived flag for whether the possession-ending event should count as a real possession. |
| `possessionBoundaryReason` | `string` | Derived short reason code for the possession boundary. |
| `foulsToGiveOffense` | `int64` | Derived remaining fouls to give for the offense team after the event. |
| `foulsToGiveDefense` | `int64` | Derived remaining fouls to give for the defense team after the event. |
| `isSecondChanceEvent` | `bool` | Derived flag for events occurring after a real offensive rebound in the same possession. |
| `isPenaltyEvent` | `bool` | Derived flag for events occurring in penalty context. |
| `isOreb` | `bool` | Derived flag for offensive rebounds. |
| `isDreb` | `bool` | Derived flag for defensive rebounds. |
| `isPlaceholderRebound` | `bool` | Derived flag for non-real rebound placeholders. |
| `isShootingFoul` | `bool` | Derived flag for shooting fouls. |
| `isTechnicalFt` | `bool` | Derived flag for technical free throws. |
| `isFlagrantFt` | `bool` | Derived flag for flagrant free throws. |
| `isBadPassTurnover` | `bool` | Derived flag for bad-pass turnovers. |
| `isLostBallTurnover` | `bool` | Derived flag for lost-ball turnovers. |
| `isTravelTurnover` | `bool` | Derived flag for traveling turnovers. |
| `isShotClockTurnover` | `bool` | Derived flag for shot-clock turnovers. |
| `teamStartingPeriodWithBall` | `int64` | Derived team id that started the period with the ball, only populated on period-start rows. |
| `isPeriodStartEvent` | `bool` | Derived flag for explicit period-start marker rows. |
| `isPeriodEndEvent` | `bool` | Derived flag for explicit period-end marker rows. |
| `linkedShotActionNumber` | `int64` | Derived linked missed-shot action number for rebound rows. |
| `reboundOfMissedShotFlag` | `bool` | Derived flag for rebounds linked to a missed shot or missed free throw. |
| `freeThrowTripSequenceNum` | `int64` | Derived free-throw position within the trip, parsed from `subType`. |
| `freeThrowTripSize` | `int64` | Derived total number of shots in the free-throw trip, parsed from `subType`. |

## `silver/on_court_state`

Grain: one row per continuous lineup stint within a game and period.

### Design Notes

- Stints are broken at grouped substitution boundaries.
- The table is intended to be the canonical silver lineup-state source.
- Runtime inputs are `silver/event_projection_v2` plus `silver/boxscore_player_game`.
- `lineup_valid_flag` and `lineup_issue` make reconstruction quality explicit instead of silently trusting every stint.

| Column | Type | Description |
| --- | --- | --- |
| `gameId` | `string` | NBA natural game identifier. |
| `period` | `int64` | Period number for the stint. |
| `stint_id` | `int64` | Monotonic stint identifier within the game. |
| `start_orderNumber` | `int64` | Starting event order number for the stint window. |
| `end_orderNumber` | `int64` | Ending event order number for the stint window. |
| `start_actionNumber` | `int64` | Starting action number for the stint window. |
| `end_actionNumber` | `int64` | Ending action number for the stint window. |
| `start_clock` | `string` | Period clock at the start of the stint. |
| `end_clock` | `string` | Period clock at the end of the stint. |
| `start_timeActual_utc` | `timestamp[us, tz=UTC]` | UTC timestamp at the start of the stint when available. |
| `end_timeActual_utc` | `timestamp[us, tz=UTC]` | UTC timestamp at the end of the stint when available. |
| `home_teamId` | `int64` | Home team id for the game. |
| `away_teamId` | `int64` | Away team id for the game. |
| `home_personIds` | `list<int64>` | Sorted home lineup player ids active for the stint. |
| `away_personIds` | `list<int64>` | Sorted away lineup player ids active for the stint. |
| `lineup_valid_flag` | `int64` | `1` when the stint lineup is internally valid, `0` when reconstruction issues were detected. |
| `lineup_issue` | `string` | Pipe-delimited issue text explaining why the stint was marked invalid. |

## `silver/possessions`

Grain: one row per possession.

### Design Notes

- Possessions are segmented from raw CDN play-by-play using vendored `pbpstats` live possession logic.
- Lineup context is stamped from `silver/on_court_state`.
- `lineupValidFlag` and `lineupIssue` describe whether a possession maps cleanly to one lineup context per side.

| Column | Type | Description |
| --- | --- | --- |
| `gameId` | `string` | NBA natural game identifier. |
| `possessionNumber` | `int64` | Monotonic possession number within the game. |
| `possessionNumberInPeriod` | `int64` | Possession number within the period. |
| `period` | `int64` | Period number for the possession. |
| `startActionNumber` | `int64` | First action number in the possession span. |
| `endActionNumber` | `int64` | Possession-ending action number. |
| `startOrderNumber` | `int64` | First order number in the possession span. |
| `endOrderNumber` | `int64` | Possession-ending order number. |
| `startClock` | `string` | Clock at possession start. |
| `endClock` | `string` | Clock at possession end. |
| `startTimeActualUtc` | `timestamp[us, tz=UTC]` | UTC timestamp at possession start when available. |
| `endTimeActualUtc` | `timestamp[us, tz=UTC]` | UTC timestamp at possession end when available. |
| `secondsElapsed` | `double` | Derived elapsed seconds from possession start to end. |
| `offenseTeamId` | `int64` | Possession offense team id. |
| `defenseTeamId` | `int64` | Possession defense team id. |
| `offenseHomeAway` | `string` | Side label for the possession offense team. |
| `defenseHomeAway` | `string` | Side label for the possession defense team. |
| `startScoreMargin` | `int64` | Score margin at possession start from the offense team's perspective. |
| `endScoreMargin` | `int64` | Score margin at possession end from the offense team's perspective. |
| `pointsScoredOnPossession` | `int64` | Total points scored by the offense during the possession. |
| `possessionStartType` | `string` | Derived possession-start classification. |
| `possessionEndType` | `string` | Derived possession-end classification. |
| `possessionBoundaryReason` | `string` | Boundary reason carried from the ending event semantics. |
| `possessionHasTimeout` | `bool` | True when the possession contains a timeout. |
| `previousPossessionHasTimeout` | `bool` | True when the immediately previous possession contained a timeout affecting context. |
| `isSecondChancePossession` | `bool` | True when the possession contains second-chance context. |
| `isPenaltyPossession` | `bool` | True when the possession contains penalty context. |
| `countsAsPossession` | `bool` | True when the possession should count as a real possession in possession-based analytics. |
| `previousPossessionNumber` | `int64` | Previous possession number in the game. |
| `nextPossessionNumber` | `int64` | Next possession number in the game. |
| `previousPossessionEndingActionNumber` | `int64` | Ending action number of the previous possession. |
| `homeLineupId` | `string` | Home lineup id stamped from `silver/on_court_state` when the possession maps cleanly to one lineup. |
| `awayLineupId` | `string` | Away lineup id stamped from `silver/on_court_state` when the possession maps cleanly to one lineup. |
| `lineupValidFlag` | `int64` | `1` when lineup context was stamped cleanly, `0` when the possession crossed unresolved lineup states. |
| `lineupIssue` | `string` | Pipe-delimited issue text for lineup stamping problems. |
| `fieldGoalAttempts` | `int64` | Count of field-goal attempts in the possession. |
| `freeThrowAttempts` | `int64` | Count of free-throw attempts in the possession. |
| `turnovers` | `int64` | Count of turnovers in the possession. |
| `offensiveRebounds` | `int64` | Count of real offensive rebounds in the possession. |
| `madeFieldGoals` | `int64` | Count of made field goals in the possession. |

## Maintenance Notes

- If `silver/playbyplay` semantic columns change, update this file.
- If `silver/on_court_state` or `silver/possessions` grain changes, update the grain descriptions first, then the column notes.
- This file is intended to document semantic meaning. For runtime validation and orchestration details, use [SILVER_RUNBOOK.md](pipelines/athena/transform/silver/SILVER_RUNBOOK.md).
