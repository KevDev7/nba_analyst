from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa

from pipelines.athena.transform.gold import transform_to_extended_player_dim_parquet as extended_player_dim


def _table_from_rows(rows: list[dict[str, object]], columns: list[str]) -> pa.Table:
    normalized_rows = [{column: row.get(column) for column in columns} for row in rows]
    return pa.Table.from_pylist(normalized_rows)


def test_build_current_person_ids_only_keeps_current_dim_rows() -> None:
    dim_player_table = _table_from_rows(
        [
            {"person_id": 1631119, "is_current": 1},
            {"person_id": 42, "is_current": 1},
            {"person_id": 9999999, "is_current": 0},
        ],
        extended_player_dim.DIM_PLAYER_REQUIRED_COLUMNS,
    )

    actual = extended_player_dim.build_current_person_ids(dim_player_table)

    assert actual == [42, 1631119]


def test_build_bbr_by_person_id_uses_only_accepted_bridge_rows() -> None:
    bridge_table = _table_from_rows(
        [
            {
                "nba_person_id": 1631119,
                "basketball_reference_player_id": "willija07",
                "match_method": "manual_owner_override",
                "match_confidence": 1.0,
            },
            {
                "nba_person_id": 9999999,
                "basketball_reference_player_id": "oldplay01",
                "match_method": "exact_full_name_unique",
                "match_confidence": 0.8,
            },
        ],
        extended_player_dim.BBR_BRIDGE_REQUIRED_COLUMNS,
    )
    bbr_profile_table = _table_from_rows(
        [
            {
                "basketball_reference_player_id": "willija07",
                "player_profile_url": "https://www.basketball-reference.com/players/w/willija07.html",
                "formal_name": "Jaylin Michael Williams",
                "position_raw": "Power Forward and Center",
                "height_raw": "6-9",
                "height_cm": 206,
                "weight_kg": 109,
                "college_raw": "Arkansas",
                "nba_debut_date": date(2022, 10, 19),
                "hall_of_fame_flag": 0,
                "headshot_url": "https://cdn.example.com/jaylin.png",
            }
        ],
        extended_player_dim.BBR_PROFILE_REQUIRED_COLUMNS,
    )

    actual = extended_player_dim.build_bbr_by_person_id(bridge_table, bbr_profile_table)

    assert actual[1631119]["basketball_reference_player_id"] == "willija07"
    assert actual[1631119]["bbr_match_method"] == "manual_owner_override"
    assert actual[1631119]["bbr_formal_name"] == "Jaylin Michael Williams"
    assert actual[9999999]["basketball_reference_player_id"] == "oldplay01"


def test_build_rows_is_current_population_scoped_and_leaves_unmatched_null() -> None:
    current_person_ids = [42, 1631119]
    current_profile_by_person = {
        1631119: {
            "player_name_short": "J. Williams",
            "latest_jersey_number": "6",
            "latest_status": "Active",
            "position_group": "big",
            "first_seen_game_date": date(2022, 10, 19),
            "last_seen_game_date": date(2025, 4, 10),
            "first_season_played": "2022-23",
            "last_season_played": "2024-25",
            "is_guard": 0,
            "is_forward": 1,
            "is_center": 1,
        }
    }
    bbr_by_person_id = {
        1631119: {
            "basketball_reference_player_id": "willija07",
            "bbr_match_method": "manual_owner_override",
            "bbr_match_confidence": 1.0,
            "bbr_formal_name": "Jaylin Michael Williams",
            "bbr_draft_team_raw": "Seattle SuperSonics",
            "bbr_headshot_url": "https://cdn.example.com/jaylin.png",
        },
        9999999: {
            "basketball_reference_player_id": "oldplay01",
            "bbr_match_method": "exact_full_name_unique",
            "bbr_match_confidence": 0.8,
        },
    }

    actual = extended_player_dim.build_rows(current_person_ids, current_profile_by_person, bbr_by_person_id)

    assert len(actual) == 2
    by_person = {row["person_id"]: row for row in actual}
    assert set(by_person) == {42, 1631119}

    matched = by_person[1631119]
    assert matched["basketball_reference_player_id"] == "willija07"
    assert matched["bbr_match_method"] == "manual_owner_override"
    assert matched["player_name_short"] == "J. Williams"
    assert matched["first_season_played"] == "2022-23"
    assert matched["last_season_played"] == "2024-25"
    assert matched["draft_team_id"] == 1610612760
    assert matched["bbr_headshot_url"] == "https://cdn.example.com/jaylin.png"

    unmatched = by_person[42]
    assert unmatched["basketball_reference_player_id"] is None
    assert unmatched["bbr_match_method"] is None
    assert unmatched["bbr_formal_name"] is None
    assert unmatched["first_season_played"] is None
    assert unmatched["last_season_played"] is None
    assert unmatched["draft_team_id"] is None


def test_build_current_profile_map_derives_first_and_last_seasons_played() -> None:
    player_table = _table_from_rows(
        [
            {
                "gameId": "0022200001",
                "personId": 1631119,
                "teamId": 1610612760,
                "nameI": "J. Williams",
                "jerseyNum": "6",
                "status": "Active",
                "position": "F-C",
            },
            {
                "gameId": "0022401190",
                "personId": 1631119,
                "teamId": 1610612760,
                "nameI": "J. Williams",
                "jerseyNum": "6",
                "status": "Active",
                "position": "F-C",
            },
        ],
        extended_player_dim.PLAYER_REQUIRED_COLUMNS,
    )
    game_table = _table_from_rows(
        [
            {"gameId": "0022200001", "gameTimeUTC": datetime(2022, 10, 18, 23, 0, tzinfo=timezone.utc)},
            {"gameId": "0022401190", "gameTimeUTC": datetime(2025, 4, 13, 19, 30, tzinfo=timezone.utc)},
        ],
        extended_player_dim.GAME_REQUIRED_COLUMNS,
    )
    player_bio_table = _table_from_rows(
        [
            {
                "personId": 1631119,
                "guard": 0,
                "forward": 1,
                "center": 1,
            }
        ],
        extended_player_dim.PLAYER_BIO_REQUIRED_COLUMNS,
    )
    dim_team_table = _table_from_rows(
        [{"team_id": 1610612760, "is_current": 1}],
        extended_player_dim.DIM_TEAM_REQUIRED_COLUMNS,
    )

    actual = extended_player_dim.build_current_profile_map(
        player_table=player_table,
        game_table=game_table,
        player_bio_table=player_bio_table,
        dim_team_table=dim_team_table,
    )

    assert actual[1631119]["first_seen_game_date"] == date(2022, 10, 18)
    assert actual[1631119]["last_seen_game_date"] == date(2025, 4, 13)
    assert actual[1631119]["first_season_played"] == "2022-23"
    assert actual[1631119]["last_season_played"] == "2024-25"


def test_map_bbr_draft_team_id_handles_aliases_and_defunct_nulls() -> None:
    assert extended_player_dim.map_bbr_draft_team_id("Seattle SuperSonics") == 1610612760
    assert extended_player_dim.map_bbr_draft_team_id("New Jersey Nets") == 1610612751
    assert extended_player_dim.map_bbr_draft_team_id("Charlotte Bobcats") == 1610612766
    assert extended_player_dim.map_bbr_draft_team_id("Toronto Huskies") is None
