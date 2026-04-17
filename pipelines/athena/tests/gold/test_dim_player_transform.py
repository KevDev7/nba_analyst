from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa

from pipelines.athena.transform.gold import transform_to_dim_player_parquet as dim_player


def _table_from_rows(rows: list[dict[str, object]], columns: list[str]) -> pa.Table:
    normalized_rows = [{column: row.get(column) for column in columns} for row in rows]
    return pa.Table.from_pylist(normalized_rows)


def test_build_player_bio_map_prefers_more_complete_row() -> None:
    player_bio_table = _table_from_rows(
        [
            {
                "personId": 7,
                "firstName": "Lean",
                "lastName": "Player",
                "birthDate": None,
                "school": None,
                "country": None,
                "heightInches": None,
                "bodyWeightLbs": None,
                "draftYear": None,
                "draftRound": None,
                "draftNumber": None,
            },
            {
                "personId": 7,
                "firstName": "Lean",
                "lastName": "Player",
                "birthDate": date(2000, 1, 1),
                "school": "Arkansas",
                "country": "USA",
                "heightInches": 81,
                "bodyWeightLbs": 240,
                "draftYear": 2022,
                "draftRound": 2,
                "draftNumber": 34,
            },
        ],
        dim_player.PLAYER_BIO_REQUIRED_COLUMNS,
    )

    actual = dim_player.build_player_bio_map(player_bio_table)

    assert actual[7]["school"] == "Arkansas"
    assert actual[7]["draft_number"] == 34


def test_merge_bbr_birth_date_fallbacks_only_fills_missing_birth_date() -> None:
    player_bio_by_person = {
        7: {
            "first_name": "Aaron",
            "family_name": "Gordon",
            "birth_date": None,
            "school": "Arizona",
            "country": "USA",
            "height_inches": 80,
            "weight_lbs": 235,
            "draft_year": 2014,
            "draft_round": 1,
            "draft_number": 4,
        },
        8: {
            "first_name": "Kept",
            "family_name": "Date",
            "birth_date": date(2000, 1, 1),
            "school": None,
            "country": None,
            "height_inches": None,
            "weight_lbs": None,
            "draft_year": None,
            "draft_round": None,
            "draft_number": None,
        },
    }

    actual = dim_player.merge_bbr_birth_date_fallbacks(
        player_bio_by_person,
        {
            7: date(1995, 9, 16),
            8: date(1999, 12, 31),
            9: date(2001, 6, 1),
        },
    )

    assert actual[7]["birth_date"] == date(1995, 9, 16)
    assert actual[8]["birth_date"] == date(2000, 1, 1)
    assert actual[9]["birth_date"] == date(2001, 6, 1)


def test_finalize_rows_returns_lean_core_schema() -> None:
    rows = [
        {
            "player_sk": 1,
            "person_id": 1631119,
            "player_name": "Jaylin Williams",
            "first_name": "Jaylin",
            "family_name": "Williams",
            "display_name": "Jaylin Williams",
            "primary_position": "F-C",
            "latest_team_id": 1610612760,
            "latest_nba_team_id": 1610612760,
            "record_source": "test",
            "valid_from_utc": datetime(2022, 10, 19, tzinfo=timezone.utc),
            "valid_to_utc": None,
            "is_current": 1,
        }
    ]
    player_bio_by_person = {
        1631119: {
            "birth_date": date(2002, 6, 29),
            "school": "Arkansas",
            "country": "USA",
            "height_inches": 81,
            "weight_lbs": 240,
            "draft_year": 2022,
            "draft_round": 2,
            "draft_number": 34,
        }
    }

    actual = dim_player.finalize_rows(rows, player_bio_by_person)

    assert len(actual) == 1
    row = actual[0]
    assert row["person_id"] == 1631119
    assert row["draft_number"] == 34
    assert row["latest_team_id"] == 1610612760
    assert "player_name_short" not in row
    assert "latest_jersey_number" not in row
    assert "basketball_reference_player_id" not in row
    assert "bbr_formal_name" not in row


def test_tracked_cols_only_include_exposed_scd2_fields() -> None:
    assert dim_player.TRACKED_COLS == [
        "player_name",
        "first_name",
        "family_name",
        "display_name",
        "primary_position",
        "latest_team_id",
        "latest_nba_team_id",
    ]
