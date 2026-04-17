from __future__ import annotations

from datetime import date, datetime, timezone

import pyarrow as pa

from pipelines.athena.transform.gold.player_surface.pipeline import GoldPlayerSurfacePipeline
from pipelines.athena.transform.gold.player_surface.sources import GoldPlayerSurfaceSources


def _table_from_rows(rows: list[dict[str, object]]) -> pa.Table:
    return pa.Table.from_pylist(rows)


def test_build_player_surface_preserves_current_person_scope_and_bbr_acceptance(monkeypatch) -> None:
    pipeline = GoldPlayerSurfacePipeline()
    sources = GoldPlayerSurfaceSources(
        player_table=_table_from_rows([]),
        game_table=_table_from_rows([]),
        player_bio_table=_table_from_rows([]),
        dim_team_table=_table_from_rows([]),
        dim_player_table=_table_from_rows(
            [
                {"person_id": 1631119, "is_current": 1},
                {"person_id": 42, "is_current": 1},
                {"person_id": 9999999, "is_current": 0},
            ]
        ),
        bbr_bridge_table=_table_from_rows([]),
        bbr_profile_table=_table_from_rows([]),
    )

    monkeypatch.setattr(
        "pipelines.athena.transform.gold.player_surface.pipeline.build_dim_player_rows",
        lambda *args, **kwargs: (
            [
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
                    "created_at_utc": datetime(2026, 3, 28, tzinfo=timezone.utc),
                    "updated_at_utc": datetime(2026, 3, 28, tzinfo=timezone.utc),
                    "birth_date": date(2002, 6, 29),
                    "school": "Arkansas",
                    "country": "USA",
                    "height_inches": 81,
                    "weight_lbs": 240,
                    "draft_year": 2022,
                    "draft_round": 2,
                    "draft_number": 34,
                }
            ],
            {},
        ),
    )
    monkeypatch.setattr(
        "pipelines.athena.transform.gold.player_surface.pipeline.build_current_person_ids",
        lambda *args, **kwargs: [42, 1631119],
    )
    monkeypatch.setattr(
        "pipelines.athena.transform.gold.player_surface.pipeline.build_current_profile_map",
        lambda *args, **kwargs: {
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
        },
    )
    monkeypatch.setattr(
        "pipelines.athena.transform.gold.player_surface.pipeline.build_bbr_by_person_id",
        lambda *args, **kwargs: {
            1631119: {
                "basketball_reference_player_id": "willija07",
                "bbr_match_method": "manual_owner_override",
                "bbr_match_confidence": 1.0,
                "bbr_formal_name": "Jaylin Michael Williams",
                "bbr_draft_team_raw": "Seattle SuperSonics",
            },
            9999999: {
                "basketball_reference_player_id": "oldplay01",
                "bbr_match_method": "exact_full_name_unique",
                "bbr_match_confidence": 0.8,
            },
        },
    )

    artifacts = pipeline.build_player_surface(sources)

    assert len(artifacts.dim_player_rows) == 1
    by_person = {row["person_id"]: row for row in artifacts.extended_player_dim_rows}
    assert set(by_person) == {42, 1631119}
    assert by_person[1631119]["basketball_reference_player_id"] == "willija07"
    assert by_person[1631119]["first_season_played"] == "2022-23"
    assert by_person[1631119]["last_season_played"] == "2024-25"
    assert by_person[1631119]["draft_team_id"] == 1610612760
    assert by_person[42]["basketball_reference_player_id"] is None


def test_build_player_surface_falls_back_to_bbr_birth_date_for_dim_player() -> None:
    pipeline = GoldPlayerSurfacePipeline()
    sources = GoldPlayerSurfaceSources(
        player_table=_table_from_rows(
            [
                {
                    "gameId": "0022400001",
                    "personId": 203932,
                    "teamId": 1610612743,
                    "name": "Aaron Gordon",
                    "firstName": "Aaron",
                    "familyName": "Gordon",
                    "position": "F",
                    "nameI": "A. Gordon",
                    "jerseyNum": "32",
                    "status": "Active",
                }
            ]
        ),
        game_table=_table_from_rows(
            [{"gameId": "0022400001", "gameTimeUTC": datetime(2024, 10, 24, 0, 0, tzinfo=timezone.utc)}]
        ),
        player_bio_table=_table_from_rows(
            [
                {
                    "personId": 203932,
                    "firstName": "Aaron",
                    "lastName": "Gordon",
                    "birthDate": None,
                    "school": "Arizona",
                    "country": "USA",
                    "heightInches": 80,
                    "bodyWeightLbs": 235,
                    "draftYear": 2014,
                    "draftRound": 1,
                    "draftNumber": 4,
                    "guard": 0,
                    "forward": 1,
                    "center": 0,
                }
            ]
        ),
        dim_team_table=_table_from_rows([{"team_id": 1610612743, "is_current": 1}]),
        dim_player_table=_table_from_rows([]),
        bbr_bridge_table=_table_from_rows(
            [
                {
                    "nba_person_id": 203932,
                    "basketball_reference_player_id": "gordoaa01",
                    "match_method": "manual_owner_override",
                    "match_confidence": 1.0,
                }
            ]
        ),
        bbr_profile_table=_table_from_rows(
            [
                {
                    "basketball_reference_player_id": "gordoaa01",
                    "player_profile_url": "https://www.basketball-reference.com/players/g/gordoaa01.html",
                    "formal_name": "Aaron Addison Gordon",
                    "birth_date": date(1995, 9, 16),
                }
            ]
        ),
    )

    artifacts = pipeline.build_player_surface(sources)

    assert len(artifacts.dim_player_rows) == 1
    assert artifacts.dim_player_rows[0]["person_id"] == 203932
    assert artifacts.dim_player_rows[0]["birth_date"] == date(1995, 9, 16)
