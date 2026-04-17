from __future__ import annotations

from datetime import datetime, timezone

from pipelines.athena.transform.silver.bbr import BbrPlayerEnrichmentPipeline
from pipelines.athena.transform.silver.bbr.types import RawHtmlSnapshot


def test_build_silver_artifacts_and_gold_projection_from_injected_inputs() -> None:
    pipeline = BbrPlayerEnrichmentPipeline(
        raw_index_snapshots=[
            RawHtmlSnapshot(
                entity_id="w",
                key="raw/bball-reference/players_index/letter=w/run_date=2026-03-28/fetched_at=20260328T010203Z.html.gz",
                fetched_at_utc=datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
                last_modified_utc=datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
                html="""
                <table><tbody>
                  <tr>
                    <th data-stat="player" data-append-csv="willija07">
                      <a href="/players/w/willija07.html">Jaylin Williams</a>
                    </th>
                    <td data-stat="year_min">2022</td>
                    <td data-stat="year_max">2026</td>
                    <td data-stat="pos">C</td>
                    <td data-stat="height">6-9</td>
                    <td data-stat="weight">240</td>
                    <td data-stat="birth_date" csk="20020629">June 29, 2002</td>
                    <td data-stat="colleges"><a href="/friv/colleges.cgi?college=arkansas">Arkansas</a></td>
                  </tr>
                </tbody></table>
                """,
            )
        ],
        raw_profile_snapshots=[
            RawHtmlSnapshot(
                entity_id="willija07",
                key="raw/bball-reference/player_profile/player_id=willija07/run_date=2026-03-28/fetched_at=20260328T010203Z.html.gz",
                fetched_at_utc=datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
                last_modified_utc=datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
                html="""
                <html>
                  <head>
                    <link rel="canonical" href="https://www.basketball-reference.com/players/w/willija07.html" />
                  </head>
                  <body>
                    <div id="meta">
                      <h1><span>Jaylin Williams</span></h1>
                      <p>Jaylin Michael Williams</p>
                      <p>6-9, 240lb (206cm, 109kg)</p>
                      <p><strong>College</strong>: Arkansas</p>
                      <p><strong>Draft</strong>: Oklahoma City Thunder, 2nd round (4th pick, 34th overall), 2022 NBA Draft</p>
                    </div>
                    <div id="leaderboard_notable-awards" data-apps=1>
                      <h4>Awards</h4>
                      <div>
                        <div><span><a href='/awards/roy.html'>2022-23 Rookie of the Year (Wilt Chamberlain Trophy)</a></span></div>
                      </div>
                      <button class="show_all_trigger">1 Award</button>
                    </div>
                  </body>
                </html>
                """,
            )
        ],
        nba_player_rows=[
            {
                "personId": 1631119,
                "firstName": "Jaylin",
                "lastName": "Williams",
                "heightInches": None,
                "bodyWeightLbs": None,
                "draftYear": None,
                "draftRound": None,
                "draftNumber": None,
                "school": None,
                "guard": None,
                "forward": None,
                "center": None,
            }
        ],
    )

    artifacts = pipeline.build_silver_artifacts()

    assert len(artifacts.index_rows) == 1
    assert len(artifacts.profile_rows) == 1
    assert len(artifacts.awards_rows) == 1
    assert len(artifacts.accepted_bridge_rows) == 1
    assert len(artifacts.duplicate_nba_rows) == 0
    assert len(artifacts.ambiguous_rows) == 0
    assert artifacts.accepted_bridge_rows[0]["basketball_reference_player_id"] == "willija07"
    assert artifacts.accepted_bridge_rows[0]["match_method"] == "manual_owner_override"
    assert artifacts.awards_rows[0]["award_family"] == "roy"
    assert artifacts.awards_rows[0]["season_label"] == "2022-23"

    gold_profiles = pipeline.build_current_gold_profiles({1631119, 9999999})

    assert set(gold_profiles) == {1631119}
    assert gold_profiles[1631119].basketball_reference_player_id == "willija07"
    assert gold_profiles[1631119].bbr_formal_name == "Jaylin Michael Williams"
