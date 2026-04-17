from __future__ import annotations

from datetime import timezone

import pyarrow as pa

from pipelines.athena.transform.gold import transform_to_player_award_history_parquet as awards


def _table_from_rows(rows: list[dict[str, object]], columns: list[str]) -> pa.Table:
    normalized_rows = [{column: row.get(column) for column in columns} for row in rows]
    return pa.Table.from_pylist(normalized_rows)


def test_build_player_award_history_rows_joins_existing_bridge_and_keeps_same_season_awards() -> None:
    bridge_table = _table_from_rows(
        [
            {
                "nba_person_id": 23,
                "basketball_reference_player_id": "jordami01",
                "match_method": "exact_full_name_unique",
                "match_confidence": 0.8,
            },
            {
                "nba_person_id": 23,
                "basketball_reference_player_id": "jordami01",
                "match_method": "manual_owner_override",
                "match_confidence": 1.0,
            },
            {
                "nba_person_id": 1626164,
                "basketball_reference_player_id": "bookede01",
                "match_method": "exact_full_name_unique",
                "match_confidence": 0.8,
            },
        ],
        awards.BRIDGE_REQUIRED_COLUMNS,
    )
    awards_table = _table_from_rows(
        [
            {
                "basketball_reference_player_id": "jordami01",
                "award_family": "mvp",
                "league_code": "NBA",
                "season_label": "1987-88",
                "team_tier": None,
            },
            {
                "basketball_reference_player_id": "jordami01",
                "award_family": "mvp",
                "league_code": "NBA",
                "season_label": "1987-88",
                "team_tier": None,
            },
            {
                "basketball_reference_player_id": "jordami01",
                "award_family": "all_nba",
                "league_code": "NBA",
                "season_label": "1987-88",
                "team_tier": 1,
            },
            {
                "basketball_reference_player_id": "bookede01",
                "award_family": "all_nba",
                "league_code": "NBA",
                "season_label": "2021-22",
                "team_tier": 1,
            },
            {
                "basketball_reference_player_id": "bookede01",
                "award_family": "all_star",
                "league_code": "ABA",
                "season_label": "1974-75",
                "team_tier": None,
            },
            {
                "basketball_reference_player_id": "unmatche01",
                "award_family": "mvp",
                "league_code": "NBA",
                "season_label": "1990-91",
                "team_tier": None,
            },
        ],
        awards.AWARDS_REQUIRED_COLUMNS,
    )

    rows = awards.build_player_award_history_rows(bridge_table, awards_table)

    assert rows == [
        {
            "person_id": 23,
            "award_type": "all_nba",
            "season_year": "1987-88",
            "team_tier": 1,
        },
        {
            "person_id": 23,
            "award_type": "mvp",
            "season_year": "1987-88",
            "team_tier": None,
        },
        {
            "person_id": 1626164,
            "award_type": "all_nba",
            "season_year": "2021-22",
            "team_tier": 1,
        },
    ]


def test_finalize_rows_assigns_surrogate_keys_and_gold_metadata() -> None:
    finalized = awards.finalize_rows(
        [
            {
                "person_id": 23,
                "award_type": "mvp",
                "season_year": "1987-88",
                "team_tier": None,
            },
            {
                "person_id": 1626164,
                "award_type": "all_nba",
                "season_year": "2021-22",
                "team_tier": 1,
            },
        ]
    )

    assert [row["player_award_history_sk"] for row in finalized] == [1, 2]
    assert {row["record_source"] for row in finalized} == {awards.RECORD_SOURCE}
    assert all(row["created_at_utc"] == row["updated_at_utc"] for row in finalized)
    assert all(row["created_at_utc"].tzinfo == timezone.utc for row in finalized)


def test_player_award_history_schema_order_matches_contract() -> None:
    assert awards.TARGET_SCHEMA.names == [
        "player_award_history_sk",
        "person_id",
        "award_type",
        "season_year",
        "team_tier",
        "record_source",
        "created_at_utc",
        "updated_at_utc",
    ]
