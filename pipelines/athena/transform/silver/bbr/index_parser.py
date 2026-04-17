from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timezone
from html import unescape
from typing import Any

try:
    from ..silver_pipeline_helpers import make_quarantine_row
except ImportError:
    from silver_pipeline_helpers import make_quarantine_row  # type: ignore[no-redef]

from .types import RawHtmlSnapshot


SOURCE_PREFIX = "raw/bball-reference/players_index/"
TABLE_NAME = "bbr_player_index"
SOURCE_KEY_PATTERN = re.compile(
    r"^raw/bball-reference/players_index/letter=([a-z])/run_date=\d{4}-\d{2}-\d{2}/"
    r"fetched_at=(\d{8}T\d{6}Z)\.html\.gz$"
)
ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_PATTERN = re.compile(
    r"<t(?P<kind>[hd])(?P<attrs>[^>]*)data-stat=\"(?P<stat>[^\"]+)\"(?P<rest>[^>]*)>(?P<html>.*?)</t[hd]>",
    re.IGNORECASE | re.DOTALL,
)
ANCHOR_PATTERN = re.compile(r"<a[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<html>.*?)</a>", re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")


def null_if_empty(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_int_or_none(value: Any) -> int | None:
    value = null_if_empty(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_date_yyyymmdd(value: str | None) -> date | None:
    value = null_if_empty(value)
    if value is None:
        return None
    text = str(value).strip()
    if not re.fullmatch(r"\d{8}", text):
        return None
    return datetime.strptime(text, "%Y%m%d").date()


def strip_tags(html: str) -> str:
    text = TAG_PATTERN.sub(" ", html)
    text = unescape(text)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def parse_attribute(attrs_text: str, attribute_name: str) -> str | None:
    match = re.search(rf"""{attribute_name}=(["'])(.*?)\1""", attrs_text)
    if match is None:
        return None
    return unescape(match.group(2))


def parse_height_inches(height_raw: str | None) -> int | None:
    height_raw = null_if_empty(height_raw)
    if height_raw is None:
        return None
    match = re.fullmatch(r"(\d+)-(\d+)", str(height_raw).strip())
    if match is None:
        return None
    return int(match.group(1)) * 12 + int(match.group(2))


def parse_source_key(key: str) -> tuple[str, datetime] | None:
    match = SOURCE_KEY_PATTERN.match(key)
    if match is None:
        return None
    return match.group(1), datetime.strptime(match.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def parse_cells(row_html: str) -> dict[str, dict[str, str]]:
    cells: dict[str, dict[str, str]] = {}
    for match in CELL_PATTERN.finditer(row_html):
        stat = match.group("stat")
        attrs = (match.group("attrs") or "") + (match.group("rest") or "")
        cells[stat] = {"attrs": attrs, "html": match.group("html")}
    return cells


def extract_player_anchor(player_cell_html: str) -> tuple[str | None, str | None]:
    match = ANCHOR_PATTERN.search(player_cell_html)
    if match is None:
        return None, None
    return unescape(match.group("href")), strip_tags(match.group("html"))


def parse_colleges(colleges_html: str | None) -> tuple[str | None, int]:
    colleges_html = null_if_empty(colleges_html)
    if colleges_html is None:
        return None, 0
    colleges = [strip_tags(match.group("html")) for match in ANCHOR_PATTERN.finditer(colleges_html)]
    colleges = [college for college in colleges if college]
    if colleges:
        return "|".join(colleges), len(colleges)
    text = strip_tags(colleges_html)
    if not text:
        return None, 0
    return text, 1


def build_row(
    *,
    cells: dict[str, dict[str, str]],
    letter: str,
    source_key: str,
    source_last_modified_utc: datetime | None,
    source_snapshot_fetched_at_utc: datetime,
) -> dict[str, Any] | None:
    player_cell = cells.get("player")
    if player_cell is None:
        return None
    player_id = parse_attribute(player_cell["attrs"], "data-append-csv")
    href, player_name = extract_player_anchor(player_cell["html"])
    colleges_raw, colleges_count = parse_colleges((cells.get("colleges") or {}).get("html"))
    player_cell_text = strip_tags(player_cell["html"])
    birth_csk = parse_attribute((cells.get("birth_date") or {}).get("attrs", ""), "csk")
    profile_url = f"https://www.basketball-reference.com{href}" if href else None
    return {
        "basketball_reference_player_id": null_if_empty(player_id),
        "player_name": null_if_empty(player_name),
        "player_profile_url": null_if_empty(profile_url),
        "letter": letter,
        "year_min": to_int_or_none(strip_tags((cells.get("year_min") or {}).get("html", ""))),
        "year_max": to_int_or_none(strip_tags((cells.get("year_max") or {}).get("html", ""))),
        "position": null_if_empty(strip_tags((cells.get("pos") or {}).get("html", ""))),
        "height_raw": null_if_empty(strip_tags((cells.get("height") or {}).get("html", ""))),
        "height_inches": parse_height_inches(strip_tags((cells.get("height") or {}).get("html", ""))),
        "weight_lbs": to_int_or_none(strip_tags((cells.get("weight") or {}).get("html", ""))),
        "birth_date": parse_date_yyyymmdd(birth_csk),
        "colleges_raw": colleges_raw,
        "colleges_count": colleges_count,
        "hall_of_fame_flag": int("*" in player_cell_text),
        "source_snapshot_fetched_at_utc": source_snapshot_fetched_at_utc,
        "_meta_source_key": source_key,
        "_meta_source_last_modified_utc": source_last_modified_utc,
    }


def build_rows_from_html(
    *,
    html: str,
    letter: str,
    source_key: str,
    source_last_modified_utc: datetime | None,
    source_snapshot_fetched_at_utc: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid_rows: list[dict[str, Any]] = []
    quarantined_rows: list[dict[str, Any]] = []
    detected_at_utc = datetime.now(timezone.utc)
    for row_html in ROW_PATTERN.findall(html):
        cells = parse_cells(row_html)
        if "player" not in cells:
            continue
        row = build_row(
            cells=cells,
            letter=letter,
            source_key=source_key,
            source_last_modified_utc=source_last_modified_utc,
            source_snapshot_fetched_at_utc=source_snapshot_fetched_at_utc,
        )
        if row is None:
            continue
        missing_required = [
            column
            for column in ["basketball_reference_player_id", "player_name", "player_profile_url"]
            if row.get(column) is None
        ]
        if missing_required:
            quarantined_rows.append(
                make_quarantine_row(
                    row,
                    table_name=TABLE_NAME,
                    reason_code="missing_required_field",
                    reason_level="error",
                    reason_detail=f"Missing required fields: {', '.join(missing_required)}",
                    detected_at_utc=detected_at_utc,
                )
            )
            continue
        valid_rows.append(row)
    return valid_rows, quarantined_rows


def choose_better_duplicate(current: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    score_columns = [
        "player_name",
        "player_profile_url",
        "year_min",
        "year_max",
        "position",
        "height_inches",
        "weight_lbs",
        "birth_date",
        "colleges_raw",
    ]
    current_score = sum(1 for column in score_columns if current.get(column) is not None)
    candidate_score = sum(1 for column in score_columns if candidate.get(column) is not None)
    if candidate_score > current_score:
        return candidate
    if candidate_score < current_score:
        return current
    current_ts = current.get("source_snapshot_fetched_at_utc") or datetime.min.replace(tzinfo=timezone.utc)
    candidate_ts = candidate.get("source_snapshot_fetched_at_utc") or datetime.min.replace(tzinfo=timezone.utc)
    return candidate if candidate_ts > current_ts else current


def dedupe_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    deduped: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for row in rows:
        player_id = row["basketball_reference_player_id"]
        current = deduped.get(player_id)
        if current is None:
            deduped[player_id] = row
            continue
        duplicate_count += 1
        deduped[player_id] = choose_better_duplicate(current, row)
    return sorted(deduped.values(), key=lambda row: row["basketball_reference_player_id"]), duplicate_count


def build_index_artifacts(snapshots: list[RawHtmlSnapshot]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int, int]:
    valid_rows: list[dict[str, Any]] = []
    quarantined_rows: list[dict[str, Any]] = []
    parse_failures = 0
    for snapshot in snapshots:
        try:
            rows, quarantine = build_rows_from_html(
                html=snapshot.html,
                letter=snapshot.entity_id,
                source_key=snapshot.key,
                source_last_modified_utc=snapshot.last_modified_utc,
                source_snapshot_fetched_at_utc=snapshot.fetched_at_utc,
            )
        except Exception:
            parse_failures += 1
            continue
        valid_rows.extend(rows)
        quarantined_rows.extend(quarantine)
    deduped_rows, duplicate_count = dedupe_rows(valid_rows)
    return deduped_rows, quarantined_rows, duplicate_count, parse_failures
