from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class RawHtmlSnapshot:
    entity_id: str
    key: str
    fetched_at_utc: datetime
    last_modified_utc: datetime | None
    html: str
    s3_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BbrAcceptedMatch:
    row: dict[str, Any]


@dataclass(frozen=True)
class BbrAmbiguousMatch:
    row: dict[str, Any]


@dataclass(frozen=True)
class BbrDuplicateNbaRow:
    row: dict[str, Any]


@dataclass(frozen=True)
class BbrUnmatchedNbaRow:
    row: dict[str, Any]


@dataclass(frozen=True)
class BbrUnmatchedBbrRow:
    row: dict[str, Any]


@dataclass(frozen=True)
class BbrGoldProfile:
    basketball_reference_player_id: str | None = None
    bbr_match_method: str | None = None
    bbr_match_confidence: float | None = None
    bbr_profile_url: str | None = None
    bbr_formal_name: str | None = None
    bbr_pronunciation: str | None = None
    bbr_former_name_note: str | None = None
    bbr_nicknames_raw: str | None = None
    bbr_instagram_handle: str | None = None
    bbr_position_raw: str | None = None
    bbr_shoots: str | None = None
    bbr_height_raw: str | None = None
    bbr_height_cm: int | None = None
    bbr_weight_kg: int | None = None
    bbr_current_team_raw: str | None = None
    bbr_birth_place_raw: str | None = None
    bbr_birth_country_code: str | None = None
    bbr_death_date: date | None = None
    bbr_college_raw: str | None = None
    bbr_colleges_raw: str | None = None
    bbr_high_school_raw: str | None = None
    bbr_high_schools_raw: str | None = None
    bbr_recruiting_rank_raw: str | None = None
    bbr_recruiting_rank_year: int | None = None
    bbr_recruiting_rank_ordinal: int | None = None
    bbr_relatives_raw: str | None = None
    bbr_draft_raw: str | None = None
    bbr_draft_team_raw: str | None = None
    bbr_draft_pick_in_round: int | None = None
    bbr_draft_league: str | None = None
    bbr_draft_selection_note: str | None = None
    bbr_nba_debut_date: date | None = None
    bbr_aba_debut_date: date | None = None
    bbr_experience_years: int | None = None
    bbr_career_length_years: int | None = None
    bbr_hall_of_fame_flag: int | None = None
    bbr_hall_of_fame_role: str | None = None
    bbr_hall_of_fame_year: int | None = None
    bbr_hall_of_fame_raw: str | None = None
    bbr_headshot_url: str | None = None


@dataclass
class BbrSilverArtifacts:
    index_rows: list[dict[str, Any]] = field(default_factory=list)
    index_quarantine_rows: list[dict[str, Any]] = field(default_factory=list)
    profile_rows: list[dict[str, Any]] = field(default_factory=list)
    awards_rows: list[dict[str, Any]] = field(default_factory=list)
    accepted_bridge_rows: list[dict[str, Any]] = field(default_factory=list)
    duplicate_nba_rows: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_rows: list[dict[str, Any]] = field(default_factory=list)
    unmatched_nba_rows: list[dict[str, Any]] = field(default_factory=list)
    unmatched_bbr_rows: list[dict[str, Any]] = field(default_factory=list)
    index_duplicate_count: int = 0
    index_parse_failures: int = 0
    profile_parse_failures: int = 0
    awards_parse_failures: int = 0
    profile_warning_reason_counts: Counter[str] = field(default_factory=Counter)
    awards_warning_reason_counts: Counter[str] = field(default_factory=Counter)
