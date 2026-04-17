from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any

from .profile_parser import (
    SOURCE_PREFIX,
    extract_canonical_url,
    extract_meta_block,
    extract_page_player_name,
    null_if_empty,
    parse_source_key,
    strip_tags,
)
from .types import RawHtmlSnapshot


LEADERBOARD_START_PATTERN = re.compile(r'<div id="leaderboard_([^"]+)"', re.IGNORECASE)
SPAN_PATTERN = re.compile(r"<span>(.*?)</span>", re.IGNORECASE | re.DOTALL)
HREF_PATTERN = re.compile(r'href=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
AWARD_SLUG_PATTERN = re.compile(r"/awards/([a-z0-9_]+)\.html", re.IGNORECASE)
LEAGUE_CODE_PATTERN = re.compile(r"/(?:leagues|allstar)/([A-Z]+)_(\d{4})\.html", re.IGNORECASE)
ALL_STAR_PATTERN = re.compile(r"^(\d{4})\s+([A-Z]+)$")
ALL_LEAGUE_PATTERN = re.compile(
    r"^(\d{4}-\d{2})\s+(All-NBA|All-Defensive|All-Rookie|All-ABA)\s+\((\d)(?:st|nd|rd|th)\)$"
)
SEASON_LABEL_PATTERN = re.compile(r"^(\d{4}-\d{2})\b")

SUPPORTED_SECTION_IDS = {"notable-awards", "allstar", "all_league"}
NOTABLE_AWARD_FAMILY_BY_SLUG = {
    "mvp": "mvp",
    "finals_mvp": "finals_mvp",
    "dpoy": "dpoy",
    "smoy": "sixth_man",
    "mip": "mip",
    "roy": "roy",
}
ALL_LEAGUE_FAMILY_BY_LABEL = {
    "All-NBA": "all_nba",
    "All-Defensive": "all_defensive",
    "All-Rookie": "all_rookie",
    "All-ABA": None,
}


def season_label_from_start_year(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def extract_first_href(html_fragment: str) -> str | None:
    match = HREF_PATTERN.search(html_fragment)
    return None if match is None else null_if_empty(match.group(1))


def extract_leaderboard_blocks(html: str) -> dict[str, str]:
    matches = list(LEADERBOARD_START_PATTERN.finditer(html))
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        section_id = match.group(1)
        if section_id not in SUPPORTED_SECTION_IDS:
            continue
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        blocks[section_id] = html[start:end]
    return blocks


def parse_notable_award(span_html: str, award_label_raw: str) -> dict[str, Any] | None:
    award_reference_url = extract_first_href(span_html)
    if award_reference_url is None:
        return None
    slug_match = AWARD_SLUG_PATTERN.search(award_reference_url)
    if slug_match is None:
        return None
    award_family = NOTABLE_AWARD_FAMILY_BY_SLUG.get(slug_match.group(1).lower())
    if award_family is None:
        return None

    season_match = SEASON_LABEL_PATTERN.match(award_label_raw)
    if season_match is not None:
        season_label = season_match.group(1)
    else:
        single_year_match = re.match(r"^(\d{4})\b", award_label_raw)
        if single_year_match is None or award_family != "finals_mvp":
            return None
        season_label = season_label_from_start_year(int(single_year_match.group(1)) - 1)

    return {
        "award_family": award_family,
        "league_code": "NBA",
        "season_label": season_label,
        "team_tier": None,
        "award_label_raw": award_label_raw,
        "award_reference_url": award_reference_url,
        "source_section": "notable_awards",
    }


def parse_all_star(span_html: str, award_label_raw: str) -> dict[str, Any] | None:
    match = ALL_STAR_PATTERN.fullmatch(award_label_raw)
    if match is None:
        return None
    all_star_year = int(match.group(1))
    league_code = match.group(2)
    return {
        "award_family": "all_star",
        "league_code": league_code,
        "season_label": season_label_from_start_year(all_star_year - 1),
        "team_tier": None,
        "award_label_raw": award_label_raw,
        "award_reference_url": extract_first_href(span_html),
        "source_section": "all_star",
    }


def parse_all_league(span_html: str, award_label_raw: str) -> dict[str, Any] | None:
    match = ALL_LEAGUE_PATTERN.fullmatch(award_label_raw)
    if match is None:
        return None
    award_family = ALL_LEAGUE_FAMILY_BY_LABEL.get(match.group(2))
    if award_family is None:
        return None
    award_reference_url = extract_first_href(span_html)
    league_match = LEAGUE_CODE_PATTERN.search(award_reference_url or "")
    return {
        "award_family": award_family,
        "league_code": league_match.group(1) if league_match is not None else None,
        "season_label": match.group(1),
        "team_tier": int(match.group(3)),
        "award_label_raw": award_label_raw,
        "award_reference_url": award_reference_url,
        "source_section": "all_league",
    }


def build_rows_from_html(
    *,
    player_id: str,
    html: str,
    s3_metadata: dict[str, str],
    source_key: str,
    source_last_modified_utc: datetime | None,
    source_snapshot_fetched_at_utc: datetime,
) -> list[dict[str, Any]]:
    meta_html = extract_meta_block(html)
    if meta_html is None:
        raise ValueError("Missing profile meta block.")

    player_profile_url = extract_canonical_url(html, s3_metadata)
    page_player_name = extract_page_player_name(meta_html)
    rows: list[dict[str, Any]] = []

    blocks = extract_leaderboard_blocks(html)
    for section_id, block_html in blocks.items():
        for span_html in SPAN_PATTERN.findall(block_html):
            award_label_raw = null_if_empty(strip_tags(span_html))
            if award_label_raw is None:
                continue
            if section_id == "notable-awards":
                parsed = parse_notable_award(span_html, award_label_raw)
            elif section_id == "allstar":
                parsed = parse_all_star(span_html, award_label_raw)
            elif section_id == "all_league":
                parsed = parse_all_league(span_html, award_label_raw)
            else:
                parsed = None
            if parsed is None:
                continue
            rows.append(
                {
                    "basketball_reference_player_id": player_id,
                    "player_profile_url": player_profile_url,
                    "page_player_name": page_player_name,
                    **parsed,
                    "source_snapshot_fetched_at_utc": source_snapshot_fetched_at_utc,
                    "_meta_source_key": source_key,
                    "_meta_source_last_modified_utc": source_last_modified_utc,
                }
            )

    deduped_rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    for row in rows:
        dedupe_key = (
            row["basketball_reference_player_id"],
            row["award_family"],
            row["season_label"],
            row["team_tier"],
            row["award_reference_url"],
        )
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        deduped_rows.append(row)
    return deduped_rows


def build_award_artifacts(snapshots: list[RawHtmlSnapshot]) -> tuple[list[dict[str, Any]], int, Counter[str]]:
    rows: list[dict[str, Any]] = []
    parse_failures = 0
    warning_reason_counts: Counter[str] = Counter()
    for snapshot in snapshots:
        try:
            snapshot_rows = build_rows_from_html(
                player_id=snapshot.entity_id,
                html=snapshot.html,
                s3_metadata=snapshot.s3_metadata,
                source_key=snapshot.key,
                source_last_modified_utc=snapshot.last_modified_utc,
                source_snapshot_fetched_at_utc=snapshot.fetched_at_utc,
            )
        except Exception:
            parse_failures += 1
            continue
        if snapshot_rows:
            if snapshot_rows[0].get("player_profile_url") is None:
                warning_reason_counts["missing_player_profile_url"] += 1
            if snapshot_rows[0].get("page_player_name") is None:
                warning_reason_counts["missing_page_player_name"] += 1
        rows.extend(snapshot_rows)
    if parse_failures > 0:
        warning_reason_counts["source_parse_failures"] = parse_failures
    return rows, parse_failures, warning_reason_counts
