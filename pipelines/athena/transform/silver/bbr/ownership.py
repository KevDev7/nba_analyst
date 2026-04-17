from __future__ import annotations

from typing import Any

from .identity import MATCH_METHOD_PRIORITY, build_accepted_proposal, build_ambiguous_row, nba_metadata_completeness


def proposal_sort_key(proposal: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, int]:
    candidate = proposal["candidate"]
    nba_row = proposal["nba_row"]
    return (
        candidate["draft_match_flag"],
        candidate["school_match_flag"],
        candidate["weight_match_flag"],
        candidate["position_match_flag"],
        candidate["match_score"],
        MATCH_METHOD_PRIORITY.get(proposal["accept_reason"], -1),
        nba_metadata_completeness(nba_row),
        -nba_row["nba_person_id"],
    )


def build_bridge_row_from_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    nba_row = proposal["nba_row"]
    candidate = proposal["candidate"]
    return {
        "nba_person_id": nba_row["nba_person_id"],
        "nba_player_name": nba_row["nba_player_name"],
        "basketball_reference_player_id": candidate["basketball_reference_player_id"],
        "bbr_player_name": candidate["bbr_player_name"],
        "match_method": proposal["accept_reason"],
        "match_confidence": proposal["match_confidence"],
        "name_key": nba_row["name_key"],
        "draft_match_flag": candidate["draft_match_flag"],
        "weight_match_flag": candidate["weight_match_flag"],
        "school_match_flag": candidate["school_match_flag"],
        "position_match_flag": candidate["position_match_flag"],
        "era_sanity_flag": candidate["era_sanity_flag"],
    }


def build_duplicate_nba_row(losing: dict[str, Any], winning: dict[str, Any]) -> dict[str, Any]:
    loser_nba = losing["nba_row"]
    loser_candidate = losing["candidate"]
    winner_nba = winning["nba_row"]
    winner_candidate = winning["candidate"]
    return {
        "nba_person_id": loser_nba["nba_person_id"],
        "nba_player_name": loser_nba["nba_player_name"],
        "name_key": loser_nba["name_key"],
        "basketball_reference_player_id": loser_candidate["basketball_reference_player_id"],
        "bbr_player_name": loser_candidate["bbr_player_name"],
        "candidate_match_method": losing["accept_reason"],
        "candidate_match_score": loser_candidate["match_score"],
        "winning_nba_person_id": winner_nba["nba_person_id"],
        "winning_nba_player_name": winner_nba["nba_player_name"],
        "winning_match_method": winning["accept_reason"],
        "winning_match_score": winner_candidate["match_score"],
        "duplicate_reason": "bbr_id_claimed_by_stronger_nba_row",
    }


def resolve_bbr_ownership(proposals: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    proposals_by_bbr_id: dict[str, list[dict[str, Any]]] = {}
    for proposal in proposals:
        proposals_by_bbr_id.setdefault(proposal["candidate"]["basketball_reference_player_id"], []).append(proposal)
    winning_proposals: list[dict[str, Any]] = []
    duplicate_nba_rows: list[dict[str, Any]] = []
    for grouped_proposals in proposals_by_bbr_id.values():
        ordered = sorted(grouped_proposals, key=proposal_sort_key, reverse=True)
        winner = ordered[0]
        winning_proposals.append(winner)
        for loser in ordered[1:]:
            duplicate_nba_rows.append(build_duplicate_nba_row(loser, winner))
    winning_proposals.sort(key=lambda proposal: proposal["nba_row"]["nba_person_id"])
    duplicate_nba_rows.sort(key=lambda row: (row["basketball_reference_player_id"], row["nba_person_id"]))
    return winning_proposals, duplicate_nba_rows


def group_has_duplicate_nba_shell_rows(entries: list[dict[str, Any]]) -> bool:
    if len(entries) < 2:
        return False
    if any((entry["top_score"] or 0) > 0 for entry in entries):
        return False
    if any(entry["metadata_completeness"] > 0 for entry in entries):
        return False
    candidate_sets = {
        tuple(candidate["basketball_reference_player_id"] for candidate in entry["top_candidates"]) for entry in entries
    }
    return len(candidate_sets) == 1


def resolve_shared_name_group(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisive_entries = [
        entry
        for entry in entries
        if entry["unique_top_candidate"] and (
            entry["top_candidates"][0]["draft_match_flag"] == 1 or ((entry["top_score"] or 0) >= 15)
        )
    ]
    positive_entries = [entry for entry in entries if (entry["top_score"] or 0) > 0]
    if len(decisive_entries) == 1 and len(positive_entries) == 1:
        winner = decisive_entries[0]
        winner_candidate = winner["top_candidates"][0]
        accepted = [build_accepted_proposal(winner["nba_row"], winner_candidate, "shared_name_strongest_row_winner")]
        ambiguous = [
            build_ambiguous_row(
                entry["nba_row"],
                entry["top_candidates"],
                reason_prefix=f"shared_name_strongest_row_winner_loser:winner_bbr_id={winner_candidate['basketball_reference_player_id']}",
            )
            for entry in entries
            if entry is not winner
        ]
        return accepted, ambiguous
    if group_has_duplicate_nba_shell_rows(entries):
        return [], [
            build_ambiguous_row(entry["nba_row"], entry["top_candidates"], reason_prefix="duplicate_nba_rows_no_metadata_owner")
            for entry in entries
        ]
    return [], [
        build_ambiguous_row(entry["nba_row"], entry["top_candidates"], reason_prefix="manual_shared_name_collision")
        for entry in entries
    ]


def classify_single_unresolved_shared_name_entry(entry: dict[str, Any], accepted_proposals_for_name: list[dict[str, Any]]) -> dict[str, Any]:
    if len(accepted_proposals_for_name) == 1 and (entry["top_score"] or 0) <= 0:
        winner_bbr_id = accepted_proposals_for_name[0]["candidate"]["basketball_reference_player_id"]
        return build_ambiguous_row(
            entry["nba_row"],
            entry["top_candidates"],
            reason_prefix=f"shared_name_strongest_row_winner_loser:winner_bbr_id={winner_bbr_id}",
        )
    return build_ambiguous_row(entry["nba_row"], entry["top_candidates"], reason_prefix="manual_shared_name_collision")
