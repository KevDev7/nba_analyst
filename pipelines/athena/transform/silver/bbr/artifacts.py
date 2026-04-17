from __future__ import annotations

from typing import Any

from .identity import (
    build_accepted_proposal,
    build_ambiguous_row,
    build_bbr_rows,
    build_manual_override_proposal,
    build_nba_rows,
    build_unresolved_entry,
    choose_candidates,
)
from .ownership import (
    build_bridge_row_from_proposal,
    classify_single_unresolved_shared_name_entry,
    resolve_bbr_ownership,
    resolve_shared_name_group,
)


def build_identity_artifacts(nba_source_rows: list[dict[str, Any]], bbr_profile_source_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    nba_rows = build_nba_rows(nba_source_rows)
    bbr_rows = build_bbr_rows(bbr_profile_source_rows)
    bbr_by_name_key: dict[str, list[dict[str, Any]]] = {}
    for row in bbr_rows:
        bbr_by_name_key.setdefault(row["name_key"], []).append(row)
    accepted_proposals: list[dict[str, Any]] = []
    ambiguous_rows: list[dict[str, Any]] = []
    unmatched_nba_rows: list[dict[str, Any]] = []
    unresolved_entries: list[dict[str, Any]] = []
    for nba_row in nba_rows:
        name_candidates = bbr_by_name_key.get(nba_row["name_key"], [])
        if not name_candidates:
            unmatched_nba_rows.append(
                {
                    "nba_person_id": nba_row["nba_person_id"],
                    "nba_player_name": nba_row["nba_player_name"],
                    "name_key": nba_row["name_key"],
                    "height_inches": nba_row["height_inches"],
                    "weight_lbs": nba_row["weight_lbs"],
                    "draft_year": nba_row["draft_year"],
                    "draft_round": nba_row["draft_round"],
                    "draft_number": nba_row["draft_number"],
                    "school": nba_row["school"],
                    "primary_position": nba_row["primary_position"],
                }
            )
            continue
        manual_override = build_manual_override_proposal(nba_row, name_candidates)
        if manual_override is not None:
            accepted_proposals.append(manual_override)
            continue
        top_candidates, accept_reasons = choose_candidates(nba_row, name_candidates)
        if len(top_candidates) == 1 and accept_reasons:
            accepted_proposals.append(build_accepted_proposal(nba_row, top_candidates[0], accept_reasons[0]))
            continue
        unresolved_entries.append(build_unresolved_entry(nba_row, top_candidates))
    unresolved_entries_by_name: dict[str, list[dict[str, Any]]] = {}
    for entry in unresolved_entries:
        unresolved_entries_by_name.setdefault(entry["nba_row"]["name_key"], []).append(entry)
    accepted_proposals_by_name: dict[str, list[dict[str, Any]]] = {}
    for proposal in accepted_proposals:
        accepted_proposals_by_name.setdefault(proposal["nba_row"]["name_key"], []).append(proposal)
    for grouped_entries in unresolved_entries_by_name.values():
        if len(grouped_entries) == 1:
            entry = grouped_entries[0]
            accepted_for_name = accepted_proposals_by_name.get(entry["nba_row"]["name_key"], [])
            ambiguous_rows.append(
                classify_single_unresolved_shared_name_entry(entry, accepted_for_name)
                if accepted_for_name
                else build_ambiguous_row(entry["nba_row"], entry["top_candidates"])
            )
            continue
        shared_name_accepts, shared_name_ambiguous = resolve_shared_name_group(grouped_entries)
        accepted_proposals.extend(shared_name_accepts)
        ambiguous_rows.extend(shared_name_ambiguous)
    winning_proposals, duplicate_nba_rows = resolve_bbr_ownership(accepted_proposals)
    bridge_rows = [build_bridge_row_from_proposal(proposal) for proposal in winning_proposals]
    matched_bbr_ids = {proposal["candidate"]["basketball_reference_player_id"] for proposal in winning_proposals}
    unmatched_bbr_rows: list[dict[str, Any]] = []
    for bbr_row in bbr_rows:
        if bbr_row["basketball_reference_player_id"] in matched_bbr_ids:
            continue
        unmatched_bbr_rows.append(
            {
                "basketball_reference_player_id": bbr_row["basketball_reference_player_id"],
                "bbr_player_name": bbr_row["bbr_player_name"],
                "name_key": bbr_row["name_key"],
                "weight_lbs": bbr_row["weight_lbs"],
                "draft_year": bbr_row["draft_year"],
                "draft_round": bbr_row["draft_round"],
                "draft_pick_overall": bbr_row["draft_pick_overall"],
                "college_raw": bbr_row["school_value"],
                "current_team_raw": bbr_row["current_team_raw"],
                "position_raw": bbr_row["position_raw"],
            }
        )
    return {
        "accepted_bridge_rows": bridge_rows,
        "duplicate_nba_rows": duplicate_nba_rows,
        "ambiguous_rows": ambiguous_rows,
        "unmatched_nba_rows": unmatched_nba_rows,
        "unmatched_bbr_rows": unmatched_bbr_rows,
    }
