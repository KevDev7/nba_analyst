from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pyarrow as pa

try:
    from ..gold_transform_helpers import (
        canonical_season_year_from_date,
        normalize_game_id,
        normalize_position_group,
        parse_date_or_none,
        to_int_or_none,
        to_positive_int_or_none,
        to_str_or_none,
    )
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        canonical_season_year_from_date,
        normalize_game_id,
        normalize_position_group,
        parse_date_or_none,
        to_int_or_none,
        to_positive_int_or_none,
        to_str_or_none,
    )

from .history import build_current_nba_team_ids, build_game_time_map, build_player_bio_map, build_player_events


EXTENDED_PLAYER_DIM_RECORD_SOURCE = (
    "gold.dim_player|gold.dim_team|silver.boxscore_player_game|silver.boxscore_game|"
    "silver.players|silver.player_identity_bridge_bbr_nba|silver.bbr_player_profile"
)

# Basketball Reference exposes draft team as free-text franchise names, not NBA canonical team IDs.
# We map the franchise-lineage names that roll into today's 30 NBA teams and intentionally leave
# truly defunct or ambiguous historical teams null for now. Examples intentionally left null:
# Chicago Stags, Indianapolis Jets, Indianapolis Olympians, Pittsburgh Ironmen,
# Providence Steamrollers, St. Louis Bombers, Toronto Huskies, Washington Capitols.
NBA_DRAFT_TEAM_ID_BY_BBR_RAW: dict[str, int] = {
    "Atlanta Hawks": 1610612737,
    "Tri-Cities Blackhawks": 1610612737,
    "Milwaukee Hawks": 1610612737,
    "St. Louis Hawks": 1610612737,
    "Boston Celtics": 1610612738,
    "Brooklyn Nets": 1610612751,
    "New Jersey Nets": 1610612751,
    "Charlotte Bobcats": 1610612766,
    "Charlotte Hornets": 1610612766,
    "Chicago Bulls": 1610612741,
    "Cleveland Cavaliers": 1610612739,
    "Dallas Mavericks": 1610612742,
    "Denver Nuggets": 1610612743,
    "Detroit Pistons": 1610612765,
    "Fort Wayne Pistons": 1610612765,
    "Golden State Warriors": 1610612744,
    "Philadelphia Warriors": 1610612744,
    "San Francisco Warriors": 1610612744,
    "Houston Rockets": 1610612745,
    "San Diego Rockets": 1610612745,
    "Indiana Pacers": 1610612754,
    "Sacramento Kings": 1610612758,
    "Kansas City Kings": 1610612758,
    "Kansas City-Omaha Kings": 1610612758,
    "Cincinnati Royals": 1610612758,
    "Rochester Royals": 1610612758,
    "Los Angeles Clippers": 1610612746,
    "San Diego Clippers": 1610612746,
    "Buffalo Braves": 1610612746,
    "Los Angeles Lakers": 1610612747,
    "Minneapolis Lakers": 1610612747,
    "Memphis Grizzlies": 1610612763,
    "Vancouver Grizzlies": 1610612763,
    "Miami Heat": 1610612748,
    "Milwaukee Bucks": 1610612749,
    "Minnesota Timberwolves": 1610612750,
    "New Orleans Pelicans": 1610612740,
    "New Orleans Hornets": 1610612740,
    "New Orleans/Oklahoma City Hornets": 1610612740,
    "New York Knicks": 1610612752,
    "Oklahoma City Thunder": 1610612760,
    "Seattle SuperSonics": 1610612760,
    "Orlando Magic": 1610612753,
    "Philadelphia 76ers": 1610612755,
    "Syracuse Nationals": 1610612755,
    "Phoenix Suns": 1610612756,
    "Portland Trail Blazers": 1610612757,
    "San Antonio Spurs": 1610612759,
    "Toronto Raptors": 1610612761,
    "Utah Jazz": 1610612762,
    "New Orleans Jazz": 1610612762,
    "Washington Wizards": 1610612764,
    "Washington Bullets": 1610612764,
    "Capital Bullets": 1610612764,
    "Chicago Packers": 1610612764,
    "Chicago Zephyrs": 1610612764,
}


def map_bbr_draft_team_id(value: Any) -> int | None:
    team_raw = to_str_or_none(value)
    if team_raw is None:
        return None
    return NBA_DRAFT_TEAM_ID_BY_BBR_RAW.get(team_raw)


def build_current_person_ids(dim_player_table: pa.Table) -> list[int]:
    person_ids: list[int] = []
    for row in dim_player_table.to_pylist():
        person_id = to_positive_int_or_none(row.get("person_id"))
        if person_id is None or to_int_or_none(row.get("is_current")) != 1:
            continue
        person_ids.append(person_id)
    return sorted(set(person_ids))


def build_profile_flags_map(player_bio_table: pa.Table) -> dict[int, dict[str, int | None]]:
    def quality_score(row: dict[str, Any]) -> int:
        return sum(1 for key in ["is_guard", "is_forward", "is_center"] if row.get(key) is not None)

    best_by_person: dict[int, dict[str, int | None]] = {}
    for row in player_bio_table.to_pylist():
        person_id = to_positive_int_or_none(row.get("personId"))
        if person_id is None:
            continue
        candidate = {
            "is_guard": to_int_or_none(row.get("guard")),
            "is_forward": to_int_or_none(row.get("forward")),
            "is_center": to_int_or_none(row.get("center")),
        }
        current = best_by_person.get(person_id)
        if current is None or quality_score(candidate) > quality_score(current):
            best_by_person[person_id] = candidate
    return best_by_person


def build_current_profile_map(
    player_table: pa.Table,
    game_table: pa.Table,
    player_bio_table: pa.Table,
    dim_team_table: pa.Table,
) -> dict[int, dict[str, Any]]:
    game_time_by_id = build_game_time_map(game_table)
    player_bio_by_person = build_player_bio_map(player_bio_table)
    flags_by_person = build_profile_flags_map(player_bio_table)
    nba_team_ids = build_current_nba_team_ids(dim_team_table)
    event_rows = build_player_events(player_table, game_time_by_id, player_bio_by_person, nba_team_ids)

    latest_by_person: dict[int, dict[str, Any]] = {}
    first_seen: dict[int, date | None] = {}
    last_seen: dict[int, date | None] = {}
    latest_details: dict[int, dict[str, Any]] = {}
    latest_sort_key_by_person: dict[int, tuple[datetime, str]] = {}

    for row in player_table.to_pylist():
        person_id = to_positive_int_or_none(row.get("personId"))
        game_id = normalize_game_id(row.get("gameId"))
        if person_id is None or game_id is None:
            continue
        game_key = game_time_by_id.get(game_id)
        sort_key = (game_key or datetime.min.replace(tzinfo=timezone.utc), game_id)
        current_sort_key = latest_sort_key_by_person.get(person_id)
        if current_sort_key is None or sort_key > current_sort_key:
            latest_sort_key_by_person[person_id] = sort_key
            latest_details[person_id] = {
                "player_name_short": to_str_or_none(row.get("nameI")),
                "latest_jersey_number": to_str_or_none(row.get("jerseyNum")),
                "latest_status": to_str_or_none(row.get("status")),
                "primary_position": to_str_or_none(row.get("position")),
            }

    for row in event_rows:
        person_id = to_positive_int_or_none(row.get("person_id"))
        game_date = parse_date_or_none(row.get("game_date"))
        game_time = row.get("game_time_utc")
        game_id = to_str_or_none(row.get("game_id")) or ""
        if person_id is None:
            continue
        if game_date is not None:
            current_first = first_seen.get(person_id)
            current_last = last_seen.get(person_id)
            if current_first is None or game_date < current_first:
                first_seen[person_id] = game_date
            if current_last is None or game_date > current_last:
                last_seen[person_id] = game_date
        sort_key = (game_time or datetime.min.replace(tzinfo=timezone.utc), game_id)
        current_sort_key = latest_by_person.get(person_id, {}).get("_sort_key")
        if current_sort_key is None or sort_key > current_sort_key:
            latest_by_person[person_id] = {
                "_sort_key": sort_key,
                "position_group": normalize_position_group(
                    latest_details.get(person_id, {}).get("primary_position") or row.get("primary_position")
                ),
            }

    output: dict[int, dict[str, Any]] = {}
    for person_id in set(first_seen) | set(last_seen) | set(latest_details) | set(flags_by_person):
        output[person_id] = {
            "player_name_short": latest_details.get(person_id, {}).get("player_name_short"),
            "latest_jersey_number": latest_details.get(person_id, {}).get("latest_jersey_number"),
            "latest_status": latest_details.get(person_id, {}).get("latest_status"),
            "position_group": latest_by_person.get(person_id, {}).get("position_group"),
            "first_seen_game_date": first_seen.get(person_id),
            "last_seen_game_date": last_seen.get(person_id),
            "first_season_played": canonical_season_year_from_date(first_seen.get(person_id)),
            "last_season_played": canonical_season_year_from_date(last_seen.get(person_id)),
            "is_guard": flags_by_person.get(person_id, {}).get("is_guard"),
            "is_forward": flags_by_person.get(person_id, {}).get("is_forward"),
            "is_center": flags_by_person.get(person_id, {}).get("is_center"),
        }
    return output


def build_extended_rows(
    current_person_ids: list[int],
    current_profile_by_person: dict[int, dict[str, Any]],
    bbr_by_person_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for person_id in current_person_ids:
        profile = current_profile_by_person.get(person_id, {})
        bbr = bbr_by_person_id.get(person_id, {})
        rows.append(
            {
                "person_id": person_id,
                "player_name_short": profile.get("player_name_short"),
                "latest_jersey_number": profile.get("latest_jersey_number"),
                "latest_status": profile.get("latest_status"),
                "position_group": profile.get("position_group"),
                "first_seen_game_date": profile.get("first_seen_game_date"),
                "last_seen_game_date": profile.get("last_seen_game_date"),
                "first_season_played": profile.get("first_season_played"),
                "last_season_played": profile.get("last_season_played"),
                "is_guard": profile.get("is_guard"),
                "is_forward": profile.get("is_forward"),
                "is_center": profile.get("is_center"),
                "basketball_reference_player_id": bbr.get("basketball_reference_player_id"),
                "bbr_match_method": bbr.get("bbr_match_method"),
                "bbr_match_confidence": bbr.get("bbr_match_confidence"),
                "bbr_profile_url": bbr.get("bbr_profile_url"),
                "bbr_formal_name": bbr.get("bbr_formal_name"),
                "bbr_pronunciation": bbr.get("bbr_pronunciation"),
                "bbr_former_name_note": bbr.get("bbr_former_name_note"),
                "bbr_nicknames_raw": bbr.get("bbr_nicknames_raw"),
                "bbr_instagram_handle": bbr.get("bbr_instagram_handle"),
                "bbr_position_raw": bbr.get("bbr_position_raw"),
                "bbr_shoots": bbr.get("bbr_shoots"),
                "bbr_height_raw": bbr.get("bbr_height_raw"),
                "bbr_height_cm": bbr.get("bbr_height_cm"),
                "bbr_weight_kg": bbr.get("bbr_weight_kg"),
                "bbr_current_team_raw": bbr.get("bbr_current_team_raw"),
                "bbr_birth_place_raw": bbr.get("bbr_birth_place_raw"),
                "bbr_birth_country_code": bbr.get("bbr_birth_country_code"),
                "bbr_death_date": bbr.get("bbr_death_date"),
                "bbr_college_raw": bbr.get("bbr_college_raw"),
                "bbr_colleges_raw": bbr.get("bbr_colleges_raw"),
                "bbr_high_school_raw": bbr.get("bbr_high_school_raw"),
                "bbr_high_schools_raw": bbr.get("bbr_high_schools_raw"),
                "bbr_recruiting_rank_raw": bbr.get("bbr_recruiting_rank_raw"),
                "bbr_recruiting_rank_year": bbr.get("bbr_recruiting_rank_year"),
                "bbr_recruiting_rank_ordinal": bbr.get("bbr_recruiting_rank_ordinal"),
                "bbr_relatives_raw": bbr.get("bbr_relatives_raw"),
                "bbr_draft_raw": bbr.get("bbr_draft_raw"),
                "bbr_draft_team_raw": bbr.get("bbr_draft_team_raw"),
                "draft_team_id": map_bbr_draft_team_id(bbr.get("bbr_draft_team_raw")),
                "bbr_draft_pick_in_round": bbr.get("bbr_draft_pick_in_round"),
                "bbr_draft_league": bbr.get("bbr_draft_league"),
                "bbr_draft_selection_note": bbr.get("bbr_draft_selection_note"),
                "bbr_nba_debut_date": bbr.get("bbr_nba_debut_date"),
                "bbr_aba_debut_date": bbr.get("bbr_aba_debut_date"),
                "bbr_experience_years": bbr.get("bbr_experience_years"),
                "bbr_career_length_years": bbr.get("bbr_career_length_years"),
                "bbr_hall_of_fame_flag": bbr.get("bbr_hall_of_fame_flag"),
                "bbr_hall_of_fame_role": bbr.get("bbr_hall_of_fame_role"),
                "bbr_hall_of_fame_year": bbr.get("bbr_hall_of_fame_year"),
                "bbr_hall_of_fame_raw": bbr.get("bbr_hall_of_fame_raw"),
                "bbr_headshot_url": bbr.get("bbr_headshot_url"),
                "record_source": EXTENDED_PLAYER_DIM_RECORD_SOURCE,
                "created_at_utc": run_ts,
                "updated_at_utc": run_ts,
            }
        )
    return rows
