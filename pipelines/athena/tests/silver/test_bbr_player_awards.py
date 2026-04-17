from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


SILVER_TRANSFORM_DIR = Path(__file__).resolve().parents[2] / "transform" / "silver"
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

from bbr.awards_parser import build_award_artifacts
from bbr.types import RawHtmlSnapshot
import build_silver_bbr_player_awards as awards


def test_bbr_player_awards_schema_order_matches_contract() -> None:
    assert awards.TARGET_SCHEMA.names == [
        "basketball_reference_player_id",
        "player_profile_url",
        "page_player_name",
        "source_section",
        "award_family",
        "league_code",
        "season_label",
        "team_tier",
        "award_label_raw",
        "award_reference_url",
        "source_snapshot_fetched_at_utc",
        "_meta_pipeline_run_id",
        "_meta_ingested_at_utc",
        "_meta_source_system",
        "_meta_source_key",
        "_meta_source_last_modified_utc",
        "_meta_schema_version",
    ]


def test_build_award_artifacts_parses_supported_awards_and_team_tiers() -> None:
    snapshot = RawHtmlSnapshot(
        entity_id="curryst01",
        key="raw/bball-reference/player_profile/player_id=curryst01/run_date=2026-03-28/fetched_at=20260328T010203Z.html.gz",
        fetched_at_utc=datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
        last_modified_utc=datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        html="""
        <html>
          <head>
            <link rel="canonical" href="https://www.basketball-reference.com/players/c/curryst01.html" />
          </head>
          <body>
            <div id="meta">
              <h1><span>Stephen Curry</span></h1>
            </div>
            <div id="leaderboard_notable-awards" data-apps=5>
              <h4>Awards</h4>
              <div>
                <div><span><a href='/awards/mvp.html'>2014-15 Most Valuable Player (Michael Jordan Trophy)</a></span></div>
                <div><span><a href='/awards/finals_mvp.html'>2022 Finals Most Valuable Player (Bill Russell Trophy)</a></span></div>
                <div><span><a href='/awards/all_star_mvp.html'>2022 All-Star Game Most Valuable Player</a></span></div>
              </div>
              <button class="show_all_trigger">3 Awards</button>
            </div>
            <div id="leaderboard_allstar" data-apps=2>
              <h4>All-Star Games</h4>
              <div>
                <div><span><a href="/allstar/NBA_2015.html">2015 NBA</a></span></div>
                <div><span><a href="/allstar/NBA_2022.html">2022 NBA</a></span></div>
              </div>
              <button class="show_all_trigger">2 All-Star Games</button>
            </div>
            <div id="leaderboard_all_league" data-apps=5>
              <h4>All-League</h4>
              <div>
                <div><span><a href='/leagues/NBA_2010.html'>2009-10</a> All-Rookie (1st)</span></div>
                <div><span><a href='/leagues/NBA_2015.html'>2014-15</a> All-NBA (1st)</span></div>
                <div><span><a href='/leagues/NBA_2018.html'>2017-18</a> All-NBA (3rd)</span></div>
                <div><span><a href='/leagues/NBA_2016.html'>2015-16</a> All-Defensive (2nd)</span></div>
                <div><span><a href='/leagues/ABA_1975.html'>1974-75</a> All-ABA (1st)</span></div>
              </div>
              <button class="show_all_trigger">5 All-League</button>
            </div>
          </body>
        </html>
        """,
    )

    rows, parse_failures, warning_reason_counts = build_award_artifacts([snapshot])

    assert parse_failures == 0
    assert warning_reason_counts == {}
    assert rows == [
        {
            "basketball_reference_player_id": "curryst01",
            "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
            "page_player_name": "Stephen Curry",
            "award_family": "mvp",
            "league_code": "NBA",
            "season_label": "2014-15",
            "team_tier": None,
            "award_label_raw": "2014-15 Most Valuable Player (Michael Jordan Trophy)",
            "award_reference_url": "/awards/mvp.html",
            "source_section": "notable_awards",
            "source_snapshot_fetched_at_utc": datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
            "_meta_source_key": snapshot.key,
            "_meta_source_last_modified_utc": datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        },
        {
            "basketball_reference_player_id": "curryst01",
            "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
            "page_player_name": "Stephen Curry",
            "award_family": "finals_mvp",
            "league_code": "NBA",
            "season_label": "2021-22",
            "team_tier": None,
            "award_label_raw": "2022 Finals Most Valuable Player (Bill Russell Trophy)",
            "award_reference_url": "/awards/finals_mvp.html",
            "source_section": "notable_awards",
            "source_snapshot_fetched_at_utc": datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
            "_meta_source_key": snapshot.key,
            "_meta_source_last_modified_utc": datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        },
        {
            "basketball_reference_player_id": "curryst01",
            "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
            "page_player_name": "Stephen Curry",
            "award_family": "all_star",
            "league_code": "NBA",
            "season_label": "2014-15",
            "team_tier": None,
            "award_label_raw": "2015 NBA",
            "award_reference_url": "/allstar/NBA_2015.html",
            "source_section": "all_star",
            "source_snapshot_fetched_at_utc": datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
            "_meta_source_key": snapshot.key,
            "_meta_source_last_modified_utc": datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        },
        {
            "basketball_reference_player_id": "curryst01",
            "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
            "page_player_name": "Stephen Curry",
            "award_family": "all_star",
            "league_code": "NBA",
            "season_label": "2021-22",
            "team_tier": None,
            "award_label_raw": "2022 NBA",
            "award_reference_url": "/allstar/NBA_2022.html",
            "source_section": "all_star",
            "source_snapshot_fetched_at_utc": datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
            "_meta_source_key": snapshot.key,
            "_meta_source_last_modified_utc": datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        },
        {
            "basketball_reference_player_id": "curryst01",
            "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
            "page_player_name": "Stephen Curry",
            "award_family": "all_rookie",
            "league_code": "NBA",
            "season_label": "2009-10",
            "team_tier": 1,
            "award_label_raw": "2009-10 All-Rookie (1st)",
            "award_reference_url": "/leagues/NBA_2010.html",
            "source_section": "all_league",
            "source_snapshot_fetched_at_utc": datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
            "_meta_source_key": snapshot.key,
            "_meta_source_last_modified_utc": datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        },
        {
            "basketball_reference_player_id": "curryst01",
            "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
            "page_player_name": "Stephen Curry",
            "award_family": "all_nba",
            "league_code": "NBA",
            "season_label": "2014-15",
            "team_tier": 1,
            "award_label_raw": "2014-15 All-NBA (1st)",
            "award_reference_url": "/leagues/NBA_2015.html",
            "source_section": "all_league",
            "source_snapshot_fetched_at_utc": datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
            "_meta_source_key": snapshot.key,
            "_meta_source_last_modified_utc": datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        },
        {
            "basketball_reference_player_id": "curryst01",
            "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
            "page_player_name": "Stephen Curry",
            "award_family": "all_nba",
            "league_code": "NBA",
            "season_label": "2017-18",
            "team_tier": 3,
            "award_label_raw": "2017-18 All-NBA (3rd)",
            "award_reference_url": "/leagues/NBA_2018.html",
            "source_section": "all_league",
            "source_snapshot_fetched_at_utc": datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
            "_meta_source_key": snapshot.key,
            "_meta_source_last_modified_utc": datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        },
        {
            "basketball_reference_player_id": "curryst01",
            "player_profile_url": "https://www.basketball-reference.com/players/c/curryst01.html",
            "page_player_name": "Stephen Curry",
            "award_family": "all_defensive",
            "league_code": "NBA",
            "season_label": "2015-16",
            "team_tier": 2,
            "award_label_raw": "2015-16 All-Defensive (2nd)",
            "award_reference_url": "/leagues/NBA_2016.html",
            "source_section": "all_league",
            "source_snapshot_fetched_at_utc": datetime(2026, 3, 28, 1, 2, 3, tzinfo=timezone.utc),
            "_meta_source_key": snapshot.key,
            "_meta_source_last_modified_utc": datetime(2026, 3, 28, 1, 5, 0, tzinfo=timezone.utc),
        },
    ]
