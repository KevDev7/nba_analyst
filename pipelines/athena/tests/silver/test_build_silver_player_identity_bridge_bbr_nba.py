from __future__ import annotations

import sys
from pathlib import Path


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

import build_silver_player_identity_bridge_bbr_nba as bridge


def test_build_nba_rows_projects_from_silver_players_contract():
    rows = [
        {
            "personId": "2037",
            "firstName": "Jamal",
            "lastName": "Crawford",
            "heightInches": "77",
            "bodyWeightLbs": "200",
            "draftYear": "2000",
            "draftRound": "1",
            "draftNumber": "8",
            "school": "Michigan",
            "guard": "1",
            "forward": None,
            "center": None,
        }
    ]

    projected = bridge.build_nba_rows(rows)

    assert projected == [
        {
            "nba_person_id": 2037,
            "nba_player_name": "Jamal Crawford",
            "name_key": "jamal crawford",
            "exact_name_key": "jamal crawford",
            "height_inches": 77,
            "weight_lbs": 200,
            "draft_year": 2000,
            "draft_round": 1,
            "draft_number": 8,
            "school": "Michigan",
            "school_key": "michigan",
            "primary_position": "G",
            "position_tokens": {"G"},
        }
    ]


def test_score_candidate_matches_databricks_secondary_scoring_without_era_penalty():
    nba_row = {
        "draft_year": 2000,
        "draft_round": 1,
        "draft_number": 8,
        "weight_lbs": 200,
        "school_key": "michigan",
        "position_tokens": {"G"},
    }
    bbr_row = {
        "draft_year": 2000,
        "draft_round": 1,
        "draft_pick_overall": 8,
        "weight_lbs": 200,
        "school_key": "michigan",
        "position_tokens": {"G"},
    }

    score, evidence = bridge.score_candidate(nba_row, bbr_row)

    assert score == 121
    assert evidence == {
        "draft_match_flag": 1,
        "weight_match_flag": 1,
        "school_match_flag": 1,
        "position_match_flag": 1,
        "era_sanity_flag": 1,
    }


def test_metadata_constants_match_databricks_bridge_contract():
    assert bridge.NBA_SOURCE_KEY == "silver/players.parquet"
    assert bridge.META_SOURCE_SYSTEM == "silver_players|silver_bbr_player_profile"
    assert bridge.META_SOURCE_KEY == "legacy_gold.silver.players|legacy_gold.silver.bbr_player_profile"


def test_choose_candidates_accepts_unique_exact_name_when_not_blocked():
    nba_row = {
        "name_key": "jamal crawford",
        "exact_name_key": "jamal crawford",
        "draft_year": None,
        "draft_round": None,
        "draft_number": None,
        "weight_lbs": None,
        "school_key": None,
        "position_tokens": set(),
    }
    bbr_candidates = [
        {
            "basketball_reference_player_id": "crawfja01",
            "bbr_player_name": "Jamal Crawford",
            "name_key": "jamal crawford",
            "exact_name_key": "jamal crawford",
            "draft_year": None,
            "draft_round": None,
            "draft_pick_overall": None,
            "weight_lbs": None,
            "school_key": None,
            "position_tokens": set(),
        }
    ]

    candidates, reasons = bridge.choose_candidates(nba_row, bbr_candidates)

    assert len(candidates) == 1
    assert reasons == ["exact_full_name_unique"]


def test_choose_candidates_does_not_auto_accept_blocklisted_name():
    nba_row = {
        "name_key": "jaylin williams",
        "exact_name_key": "jaylin williams",
        "draft_year": None,
        "draft_round": None,
        "draft_number": None,
        "weight_lbs": None,
        "school_key": None,
        "position_tokens": set(),
    }
    bbr_candidates = [
        {
            "basketball_reference_player_id": "willija01",
            "bbr_player_name": "Jaylin Williams",
            "name_key": "jaylin williams",
            "exact_name_key": "jaylin williams",
            "draft_year": None,
            "draft_round": None,
            "draft_pick_overall": None,
            "weight_lbs": None,
            "school_key": None,
            "position_tokens": set(),
        }
    ]

    candidates, reasons = bridge.choose_candidates(nba_row, bbr_candidates)

    assert len(candidates) == 1
    assert reasons == []


def test_suffix_preserving_normalization_keeps_jr_distinct() -> None:
    assert bridge.normalize_text("Tim Hardaway Jr.") == "tim hardaway"
    assert bridge.normalize_text_preserve_suffix("Tim Hardaway Jr.") == "tim hardaway jr"
    assert bridge.normalize_text_preserve_suffix("Gary Payton II") == "gary payton ii"
    assert bridge.normalize_text_preserve_suffix("John Lucas III") == "john lucas iii"


def test_normalization_collapses_dotted_initials() -> None:
    assert bridge.normalize_text("AJ Green") == "aj green"
    assert bridge.normalize_text("A.J. Green") == "aj green"
    assert bridge.normalize_text_preserve_suffix("AJ Green") == "aj green"
    assert bridge.normalize_text_preserve_suffix("A.J. Green") == "aj green"


def test_choose_candidates_prefers_unique_suffix_preserving_exact_match() -> None:
    nba_row = {
        "name_key": "tim hardaway",
        "exact_name_key": "tim hardaway jr",
        "draft_year": None,
        "draft_round": None,
        "draft_number": None,
        "weight_lbs": None,
        "school_key": None,
        "position_tokens": set(),
    }
    bbr_candidates = [
        {
            "basketball_reference_player_id": "hardati01",
            "bbr_player_name": "Tim Hardaway",
            "name_key": "tim hardaway",
            "exact_name_key": "tim hardaway",
            "draft_year": None,
            "draft_round": None,
            "draft_pick_overall": None,
            "weight_lbs": None,
            "school_key": None,
            "position_tokens": set(),
        },
        {
            "basketball_reference_player_id": "hardati02",
            "bbr_player_name": "Tim Hardaway Jr.",
            "name_key": "tim hardaway",
            "exact_name_key": "tim hardaway jr",
            "draft_year": None,
            "draft_round": None,
            "draft_pick_overall": None,
            "weight_lbs": None,
            "school_key": None,
            "position_tokens": set(),
        },
    ]

    candidates, reasons = bridge.choose_candidates(nba_row, bbr_candidates)

    assert [candidate["basketball_reference_player_id"] for candidate in candidates] == ["hardati02"]
    assert reasons == ["exact_full_name_with_suffix_unique"]


def test_build_identity_artifacts_matches_dotted_initials_against_undotted_nba_name() -> None:
    artifacts = bridge.build_identity_artifacts(
        nba_source_rows=[
            {
                "personId": "1631260",
                "firstName": "AJ",
                "lastName": "Green",
                "heightInches": "76",
                "bodyWeightLbs": "190",
                "draftYear": "2022",
                "draftRound": None,
                "draftNumber": None,
                "school": None,
                "guard": "1",
                "forward": "0",
                "center": "0",
            }
        ],
        bbr_profile_source_rows=[
            {
                "basketball_reference_player_id": "greenaj01",
                "page_player_name": "A.J. Green",
                "draft_year": "2022",
                "draft_round": None,
                "draft_pick_overall": None,
                "weight_lbs": "190",
                "college_raw": None,
                "colleges_raw": None,
                "position_raw": "Guard",
                "current_team_raw": "Milwaukee Bucks",
            }
        ],
    )

    assert artifacts["accepted_bridge_rows"] == [
        {
            "nba_person_id": 1631260,
            "nba_player_name": "AJ Green",
            "basketball_reference_player_id": "greenaj01",
            "bbr_player_name": "A.J. Green",
            "match_method": "exact_full_name_unique",
            "match_confidence": 0.8,
            "name_key": "aj green",
            "draft_match_flag": 0,
            "weight_match_flag": 1,
            "school_match_flag": 0,
            "position_match_flag": 1,
            "era_sanity_flag": 1,
        }
    ]
    assert artifacts["unmatched_nba_rows"] == []


def test_build_manual_override_proposal_accepts_configured_owner() -> None:
    proposal = bridge.build_manual_override_proposal(
        {
            "nba_person_id": 1631119,
            "nba_player_name": "Jaylin Williams",
            "name_key": "jaylin williams",
            "height_inches": None,
            "weight_lbs": None,
            "draft_year": None,
            "draft_round": None,
            "draft_number": None,
            "school_key": None,
            "primary_position": None,
        },
        [
            {
                "basketball_reference_player_id": "willija07",
                "bbr_player_name": "Jaylin Williams",
                "exact_name_key": "jaylin williams",
                "draft_year": 2022,
                "draft_round": 2,
                "draft_pick_overall": 34,
                "weight_lbs": 240,
                "school_key": "arkansas",
                "position_tokens": {"F", "C"},
            }
        ],
    )

    assert proposal is not None
    assert proposal["accept_reason"] == "manual_owner_override"
    assert proposal["candidate"]["basketball_reference_player_id"] == "willija07"
    assert proposal["match_confidence"] == 1.0


def test_resolve_bbr_ownership_keeps_only_strongest_nba_owner() -> None:
    winning_candidate = {
        "basketball_reference_player_id": "russewa01",
        "bbr_player_name": "Walker Russell",
        "match_score": 115,
        "draft_match_flag": 1,
        "weight_match_flag": 1,
        "school_match_flag": 1,
        "position_match_flag": 0,
        "era_sanity_flag": 1,
    }
    losing_candidate = {
        "basketball_reference_player_id": "russewa01",
        "bbr_player_name": "Walker Russell",
        "match_score": 90,
        "draft_match_flag": 1,
        "weight_match_flag": 0,
        "school_match_flag": 0,
        "position_match_flag": 0,
        "era_sanity_flag": 1,
    }
    winning_proposals, duplicate_rows = bridge.resolve_bbr_ownership(
        [
            bridge.build_accepted_proposal(
                {
                    "nba_person_id": 201041,
                    "nba_player_name": "Walker Russell",
                    "name_key": "walker russell",
                    "height_inches": 72,
                    "weight_lbs": 170,
                    "draft_year": 1982,
                    "draft_round": 4,
                    "draft_number": 78,
                    "school_key": "jacksonville state",
                    "primary_position": "G",
                },
                losing_candidate,
                "unique_top_score_supported_by_multiple_secondary_checks",
            ),
            bridge.build_accepted_proposal(
                {
                    "nba_person_id": 78048,
                    "nba_player_name": "Walker Russell",
                    "name_key": "walker russell",
                    "height_inches": 77,
                    "weight_lbs": 195,
                    "draft_year": 1982,
                    "draft_round": 4,
                    "draft_number": 78,
                    "school_key": "western michigan",
                    "primary_position": "G",
                },
                winning_candidate,
                "unique_top_score_with_draft_match",
            ),
        ]
    )

    assert [proposal["nba_row"]["nba_person_id"] for proposal in winning_proposals] == [78048]
    assert duplicate_rows == [
        {
            "nba_person_id": 201041,
            "nba_player_name": "Walker Russell",
            "name_key": "walker russell",
            "basketball_reference_player_id": "russewa01",
            "bbr_player_name": "Walker Russell",
            "candidate_match_method": "unique_top_score_supported_by_multiple_secondary_checks",
            "candidate_match_score": 90,
            "winning_nba_person_id": 78048,
            "winning_nba_player_name": "Walker Russell",
            "winning_match_method": "unique_top_score_with_draft_match",
            "winning_match_score": 115,
            "duplicate_reason": "bbr_id_claimed_by_stronger_nba_row",
        }
    ]


def test_resolve_bbr_ownership_tie_breaks_on_metadata_completeness_then_person_id() -> None:
    shared_candidate = {
        "basketball_reference_player_id": "jonesma02",
        "bbr_player_name": "Mark Jones",
        "match_score": 108,
        "draft_match_flag": 1,
        "weight_match_flag": 0,
        "school_match_flag": 1,
        "position_match_flag": 0,
        "era_sanity_flag": 1,
    }
    proposal_low_id = bridge.build_accepted_proposal(
        {
            "nba_person_id": 2891,
            "nba_player_name": "Mark Jones",
            "name_key": "mark jones",
            "height_inches": 78,
            "weight_lbs": 215,
            "draft_year": 1983,
            "draft_round": 4,
            "draft_number": 82,
            "school_key": "saint bonaventure",
            "primary_position": "G",
        },
        shared_candidate,
        "unique_top_score_with_draft_match",
    )
    proposal_high_id = bridge.build_accepted_proposal(
        {
            "nba_person_id": 90000,
            "nba_player_name": "Mark Jones",
            "name_key": "mark jones",
            "height_inches": 78,
            "weight_lbs": 215,
            "draft_year": 1983,
            "draft_round": 4,
            "draft_number": 82,
            "school_key": "saint bonaventure",
            "primary_position": "G",
        },
        shared_candidate,
        "unique_top_score_with_draft_match",
    )

    winning_proposals, duplicate_rows = bridge.resolve_bbr_ownership([proposal_high_id, proposal_low_id])

    assert [proposal["nba_row"]["nba_person_id"] for proposal in winning_proposals] == [2891]
    assert duplicate_rows[0]["winning_nba_person_id"] == 2891
    assert duplicate_rows[0]["nba_person_id"] == 90000


def test_resolve_shared_name_group_accepts_strongest_row_with_weak_siblings() -> None:
    accepted, ambiguous = bridge.resolve_shared_name_group(
        [
            bridge.build_unresolved_entry(
                {
                    "nba_person_id": 77818,
                    "nba_player_name": "Jim Paxson",
                    "name_key": "jim paxson",
                    "height_inches": 78,
                    "weight_lbs": 200,
                    "draft_year": 1956,
                    "draft_round": 1,
                    "draft_number": 3,
                    "school_key": "dayton",
                    "primary_position": "G",
                },
                [
                    {
                        "basketball_reference_player_id": "paxsoji01",
                        "bbr_player_name": "Jim Paxson",
                        "match_score": -82,
                        "draft_match_flag": 0,
                        "weight_match_flag": 1,
                        "school_match_flag": 1,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    },
                    {
                        "basketball_reference_player_id": "paxsoji02",
                        "bbr_player_name": "Jim Paxson",
                        "match_score": -82,
                        "draft_match_flag": 0,
                        "weight_match_flag": 1,
                        "school_match_flag": 1,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    },
                ],
            ),
            bridge.build_unresolved_entry(
                {
                    "nba_person_id": 77819,
                    "nba_player_name": "Jim Paxson",
                    "name_key": "jim paxson",
                    "height_inches": 78,
                    "weight_lbs": 200,
                    "draft_year": 1979,
                    "draft_round": 1,
                    "draft_number": 12,
                    "school_key": "dayton",
                    "primary_position": "G",
                },
                [
                    {
                        "basketball_reference_player_id": "paxsoji02",
                        "bbr_player_name": "Jim Paxson",
                        "match_score": 118,
                        "draft_match_flag": 1,
                        "weight_match_flag": 1,
                        "school_match_flag": 1,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    }
                ],
            ),
        ]
    )

    assert [proposal["nba_row"]["nba_person_id"] for proposal in accepted] == [77819]
    assert accepted[0]["accept_reason"] == "shared_name_strongest_row_winner"
    assert ambiguous[0]["candidate_reasons"].startswith(
        "shared_name_strongest_row_winner_loser:winner_bbr_id=paxsoji02|"
    )


def test_resolve_shared_name_group_keeps_true_collision_manual() -> None:
    accepted, ambiguous = bridge.resolve_shared_name_group(
        [
            bridge.build_unresolved_entry(
                {
                    "nba_person_id": 40043,
                    "nba_player_name": "Charles Smith",
                    "name_key": "charles smith",
                    "height_inches": None,
                    "weight_lbs": None,
                    "draft_year": None,
                    "draft_round": None,
                    "draft_number": None,
                    "school_key": None,
                    "primary_position": None,
                },
                [
                    {
                        "basketball_reference_player_id": "smithch01",
                        "bbr_player_name": "Charles Smith",
                        "match_score": 0,
                        "draft_match_flag": 0,
                        "weight_match_flag": 0,
                        "school_match_flag": 0,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    },
                    {
                        "basketball_reference_player_id": "smithch02",
                        "bbr_player_name": "Charles Smith",
                        "match_score": 0,
                        "draft_match_flag": 0,
                        "weight_match_flag": 0,
                        "school_match_flag": 0,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    },
                ],
            ),
            bridge.build_unresolved_entry(
                {
                    "nba_person_id": 293,
                    "nba_player_name": "Charles Smith",
                    "name_key": "charles smith",
                    "height_inches": 82,
                    "weight_lbs": 244,
                    "draft_year": 1988,
                    "draft_round": 1,
                    "draft_number": 3,
                    "school_key": "pittsburgh",
                    "primary_position": "F",
                },
                [
                    {
                        "basketball_reference_player_id": "smithch01",
                        "bbr_player_name": "Charles Smith",
                        "match_score": 0,
                        "draft_match_flag": 0,
                        "weight_match_flag": 0,
                        "school_match_flag": 0,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    },
                    {
                        "basketball_reference_player_id": "smithch04",
                        "bbr_player_name": "Charles Smith",
                        "match_score": 0,
                        "draft_match_flag": 0,
                        "weight_match_flag": 0,
                        "school_match_flag": 0,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    },
                ],
            ),
        ]
    )

    assert accepted == []
    assert all(row["candidate_reasons"].startswith("manual_shared_name_collision|") for row in ambiguous)


def test_resolve_shared_name_group_marks_duplicate_shell_rows() -> None:
    accepted, ambiguous = bridge.resolve_shared_name_group(
        [
            bridge.build_unresolved_entry(
                {
                    "nba_person_id": 1631119,
                    "nba_player_name": "Jaylin Williams",
                    "name_key": "jaylin williams",
                    "height_inches": None,
                    "weight_lbs": None,
                    "draft_year": None,
                    "draft_round": None,
                    "draft_number": None,
                    "school_key": None,
                    "primary_position": None,
                },
                [
                    {
                        "basketball_reference_player_id": "willija07",
                        "bbr_player_name": "Jaylin Williams",
                        "match_score": 0,
                        "draft_match_flag": 0,
                        "weight_match_flag": 0,
                        "school_match_flag": 0,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    }
                ],
            ),
            bridge.build_unresolved_entry(
                {
                    "nba_person_id": 1642444,
                    "nba_player_name": "Jaylin Williams",
                    "name_key": "jaylin williams",
                    "height_inches": None,
                    "weight_lbs": None,
                    "draft_year": None,
                    "draft_round": None,
                    "draft_number": None,
                    "school_key": None,
                    "primary_position": None,
                },
                [
                    {
                        "basketball_reference_player_id": "willija07",
                        "bbr_player_name": "Jaylin Williams",
                        "match_score": 0,
                        "draft_match_flag": 0,
                        "weight_match_flag": 0,
                        "school_match_flag": 0,
                        "position_match_flag": 0,
                        "era_sanity_flag": 1,
                    }
                ],
            ),
        ]
    )

    assert accepted == []
    assert all(row["candidate_reasons"].startswith("duplicate_nba_rows_no_metadata_owner|") for row in ambiguous)


def test_classify_single_unresolved_shared_name_entry_marks_loser_against_existing_winner() -> None:
    entry = bridge.build_unresolved_entry(
        {
            "nba_person_id": 1630607,
            "nba_player_name": "Chris Smith",
            "name_key": "chris smith",
            "height_inches": None,
            "weight_lbs": None,
            "draft_year": None,
            "draft_round": None,
            "draft_number": None,
            "school_key": None,
            "primary_position": None,
        },
        [
            {
                "basketball_reference_player_id": "smithch05",
                "bbr_player_name": "Chris Smith",
                "match_score": 0,
                "draft_match_flag": 0,
                "weight_match_flag": 0,
                "school_match_flag": 0,
                "position_match_flag": 0,
                "era_sanity_flag": 1,
            }
        ],
    )
    winner = bridge.build_accepted_proposal(
        {
            "nba_person_id": 203147,
            "nba_player_name": "Chris Smith",
            "name_key": "chris smith",
            "height_inches": 74,
            "weight_lbs": 200,
            "draft_year": None,
            "draft_round": None,
            "draft_number": None,
            "school_key": "louisville",
            "primary_position": "G",
        },
        {
            "basketball_reference_player_id": "smithch05",
            "bbr_player_name": "Chris Smith",
            "match_score": 15,
            "draft_match_flag": 0,
            "weight_match_flag": 1,
            "school_match_flag": 1,
            "position_match_flag": 0,
            "era_sanity_flag": 1,
        },
        "shared_name_strongest_row_winner",
    )

    ambiguous = bridge.classify_single_unresolved_shared_name_entry(entry, [winner])

    assert ambiguous["candidate_reasons"].startswith("shared_name_strongest_row_winner_loser:winner_bbr_id=smithch05|")
