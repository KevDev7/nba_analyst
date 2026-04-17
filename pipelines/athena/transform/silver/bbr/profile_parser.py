from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timezone
from html import unescape
from typing import Any

from .types import RawHtmlSnapshot


SOURCE_PREFIX = "raw/bball-reference/player_profile/"
SOURCE_KEY_PATTERN = re.compile(
    r"^raw/bball-reference/player_profile/player_id=([^/]+)/run_date=\d{4}-\d{2}-\d{2}/"
    r"fetched_at=(\d{8}T\d{6}Z)\.html\.gz$"
)
META_START_PATTERN = re.compile(r'<div id="meta">', re.IGNORECASE)
META_END_PATTERNS = [
    re.compile(r"</div>\s*</div><!-- div#meta -->", re.IGNORECASE),
    re.compile(r'<ul id="bling">', re.IGNORECASE),
    re.compile(r'<div id="leaderboard_wrapper">', re.IGNORECASE),
]
PARAGRAPH_PATTERN = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
STRONG_PATTERN = re.compile(r"<strong[^>]*>(.*?)</strong>", re.IGNORECASE | re.DOTALL)
H1_NAME_PATTERN = re.compile(r"<h1[^>]*>\s*<span>(.*?)</span>\s*</h1>", re.IGNORECASE | re.DOTALL)
CANONICAL_LINK_PATTERN = re.compile(r'<link[^>]+rel="canonical"[^>]+href="([^"]+)"', re.IGNORECASE)
HEADSHOT_PATTERN = re.compile(r"<img[^>]+src=['\"]([^'\"]+)['\"]", re.IGNORECASE)
DATE_ATTR_PATTERN_TEMPLATE = r'data-{attribute_name}="([^"]+)"'
TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


def null_if_empty(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def strip_tags(html: str) -> str:
    text = TAG_PATTERN.sub(" ", html)
    text = unescape(text)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def normalize_label_name(label_text: str | None) -> str | None:
    label_text = null_if_empty(label_text)
    if label_text is None:
        return None
    normalized = unescape(str(label_text)).strip().rstrip(":").lower()
    normalized = NON_ALNUM_PATTERN.sub("_", normalized).strip("_")
    return normalized or None


def parse_date_iso(value: str | None) -> date | None:
    value = null_if_empty(value)
    if value is None:
        return None
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_meta_block(html: str) -> str | None:
    start_match = META_START_PATTERN.search(html)
    if start_match is None:
        return None
    start = start_match.start()
    end_candidates = []
    for pattern in META_END_PATTERNS:
        end_match = pattern.search(html, start_match.end())
        if end_match is not None:
            end_candidates.append(end_match.start())
    return html[start:] if not end_candidates else html[start:min(end_candidates)]


def extract_page_player_name(meta_html: str) -> str | None:
    match = H1_NAME_PATTERN.search(meta_html)
    if match is None:
        return None
    return null_if_empty(strip_tags(match.group(1)))


def extract_canonical_url(html: str, s3_metadata: dict[str, str]) -> str | None:
    match = CANONICAL_LINK_PATTERN.search(html)
    if match is not None:
        return null_if_empty(unescape(match.group(1)))
    return null_if_empty(s3_metadata.get("source_url"))


def extract_headshot_url(meta_html: str) -> str | None:
    match = HEADSHOT_PATTERN.search(meta_html)
    return None if match is None else null_if_empty(unescape(match.group(1)))


def parse_measurements(paragraph_text: str) -> dict[str, Any]:
    match = re.fullmatch(r"(\d+-\d+)\s*,\s*(\d+)lb\s*\((\d+)cm,\s*(\d+)kg\)", paragraph_text)
    if match is None:
        return {}
    height_raw = match.group(1)
    feet, inches = height_raw.split("-")
    return {
        "height_raw": height_raw,
        "height_inches": int(feet) * 12 + int(inches),
        "height_cm": int(match.group(3)),
        "weight_lbs": int(match.group(2)),
        "weight_kg": int(match.group(4)),
    }


def parse_labeled_value(paragraph_text: str, label_text_raw: str) -> str | None:
    match = re.match(rf"^{re.escape(label_text_raw)}\s*:\s*(.*)$", paragraph_text)
    return None if match is None else null_if_empty(match.group(1).strip())


def parse_position_and_shoots(paragraph_text: str) -> tuple[str | None, str | None]:
    match = re.match(r"^Position\s*:\s*(.*?)\s*[▪•]\s*Shoots\s*:\s*(.*)$", paragraph_text)
    if match is None:
        return None, None
    return null_if_empty(match.group(1).strip()), null_if_empty(match.group(2).strip())


def parse_attr_date_from_html(paragraph_html: str, attribute_name: str) -> date | None:
    pattern = re.compile(DATE_ATTR_PATTERN_TEMPLATE.format(attribute_name=re.escape(attribute_name)))
    match = pattern.search(paragraph_html)
    return None if match is None else parse_date_iso(match.group(1))


def parse_visible_date_from_html(paragraph_html: str) -> date | None:
    match = re.search(r'>([A-Za-z]+\s+\d{1,2},\s+\d{4})<', paragraph_html)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%B %d, %Y").date()
    except ValueError:
        return None


def parse_birth_fields(paragraph_text: str, paragraph_html: str) -> dict[str, Any]:
    value = parse_labeled_value(paragraph_text, "Born")
    birth_date = parse_attr_date_from_html(paragraph_html, "birth")
    country_match = re.search(r'<span[^>]*class="[^"]*f-i[^"]*"[^>]*>\s*([a-z]{2})\s*</span>', paragraph_html)
    birth_country_code = null_if_empty(country_match.group(1).lower()) if country_match else None
    birth_place_raw = None
    if value is not None and " in " in value:
        birth_place_raw = value.split(" in ", 1)[1].strip()
        if birth_country_code and birth_place_raw.lower().endswith(f" {birth_country_code}"):
            birth_place_raw = birth_place_raw[: -(len(birth_country_code) + 1)].strip()
    return {
        "birth_date": birth_date,
        "birth_place_raw": null_if_empty(birth_place_raw),
        "birth_country_code": birth_country_code,
    }


def parse_recruiting_rank(value: str | None) -> tuple[int | None, int | None]:
    value = null_if_empty(value)
    if value is None:
        return None, None
    match = re.search(r"(\d{4})\s*\((\d+)\)", value)
    return (None, None) if match is None else (int(match.group(1)), int(match.group(2)))


def parse_draft(value: str | None) -> dict[str, Any]:
    value = null_if_empty(value)
    if value is None:
        return {
            "draft_team_raw": None,
            "draft_round": None,
            "draft_pick_in_round": None,
            "draft_pick_overall": None,
            "draft_year": None,
            "draft_league": None,
            "draft_selection_note": None,
        }
    draft_team_raw = null_if_empty(value.split(",", 1)[0].strip())
    round_match = re.search(r"(\d+)(?:st|nd|rd|th)\s+round", value)
    pick_match = re.search(r"\((\d+)(?:st|nd|rd|th)\s+pick,\s*(\d+)(?:st|nd|rd|th)\s+overall\)", value)
    draft_match = re.search(r"(\d{4})\s+([A-Z]+)\s+Draft", value)
    note_match = re.search(r"Draft\s*\(([^)]+)\)\s*$", value)
    return {
        "draft_team_raw": draft_team_raw,
        "draft_round": int(round_match.group(1)) if round_match else None,
        "draft_pick_in_round": int(pick_match.group(1)) if pick_match else None,
        "draft_pick_overall": int(pick_match.group(2)) if pick_match else None,
        "draft_year": int(draft_match.group(1)) if draft_match else None,
        "draft_league": draft_match.group(2) if draft_match else None,
        "draft_selection_note": null_if_empty(note_match.group(1).strip()) if note_match else None,
    }


def parse_experience_years(value: str | None) -> int | None:
    value = null_if_empty(value)
    if value is None:
        return None
    match = re.search(r"(\d+)\s+year", value)
    return None if match is None else int(match.group(1))


def parse_hall_of_fame(value: str | None) -> tuple[int, str | None, int | None]:
    value = null_if_empty(value)
    if value is None:
        return 0, None, None
    match = re.search(r"Inducted as\s+(.+?)\s+in\s+(\d{4})", value)
    if match is None:
        return 1, None, None
    return 1, null_if_empty(match.group(1).strip()), int(match.group(2))


def detect_labels_in_paragraph(paragraph_html: str) -> list[str]:
    labels: list[str] = []
    for match in STRONG_PATTERN.finditer(paragraph_html):
        strong_text = strip_tags(match.group(1))
        if not strong_text:
            continue
        strong_text_compact = strong_text.strip()
        trailing_text = paragraph_html[match.end():]
        trailing_text_stripped = trailing_text.lstrip()
        is_label = strong_text_compact.endswith(":") or trailing_text_stripped.startswith(":")
        if is_label:
            labels.append(strong_text_compact.rstrip(":").strip())
    return labels


def update_unlabeled_fields(row: dict[str, Any], paragraph_text: str) -> None:
    if not paragraph_text:
        return
    measurements = parse_measurements(paragraph_text)
    if measurements:
        row.update(measurements)
        return
    if paragraph_text.startswith("(") and paragraph_text.endswith(")"):
        inner_text = paragraph_text[1:-1].strip()
        lowered = inner_text.lower()
        if "formerly known as" in lowered or "changed his name to" in lowered:
            row["former_name_note"] = null_if_empty(inner_text)
            return
        if row.get("nicknames_raw") is None:
            row["nicknames_raw"] = null_if_empty(inner_text)
        return
    if row.get("formal_name") is None:
        instagram_match = re.match(r"^(.*?)\s*[▪•]\s*Instagram\s*:\s*(.+)$", paragraph_text)
        if instagram_match is not None:
            row["formal_name"] = null_if_empty(instagram_match.group(1).strip())
            row["instagram_handle"] = null_if_empty(instagram_match.group(2).strip())
            return
        row["formal_name"] = null_if_empty(paragraph_text)


def parse_source_key(key: str) -> tuple[str, datetime] | None:
    match = SOURCE_KEY_PATTERN.match(key)
    if match is None:
        return None
    return match.group(1), datetime.strptime(match.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def build_row(
    *,
    player_id: str,
    html: str,
    s3_metadata: dict[str, str],
    source_key: str,
    source_last_modified_utc: datetime | None,
    source_snapshot_fetched_at_utc: datetime,
) -> dict[str, Any]:
    meta_html = extract_meta_block(html)
    if meta_html is None:
        raise ValueError("Missing profile meta block.")
    row: dict[str, Any] = {
        "basketball_reference_player_id": player_id,
        "player_profile_url": extract_canonical_url(html, s3_metadata),
        "page_player_name": extract_page_player_name(meta_html),
        "formal_name": None,
        "pronunciation": None,
        "former_name_note": None,
        "nicknames_raw": None,
        "instagram_handle": None,
        "position_raw": None,
        "shoots": None,
        "height_raw": None,
        "height_inches": None,
        "height_cm": None,
        "weight_lbs": None,
        "weight_kg": None,
        "current_team_raw": None,
        "birth_date": None,
        "birth_place_raw": None,
        "birth_country_code": None,
        "death_date": None,
        "college_raw": None,
        "colleges_raw": None,
        "high_school_raw": None,
        "high_schools_raw": None,
        "recruiting_rank_raw": None,
        "recruiting_rank_year": None,
        "recruiting_rank_ordinal": None,
        "relatives_raw": None,
        "draft_raw": None,
        "draft_team_raw": None,
        "draft_round": None,
        "draft_pick_in_round": None,
        "draft_pick_overall": None,
        "draft_year": None,
        "draft_league": None,
        "draft_selection_note": None,
        "nba_debut_date": None,
        "aba_debut_date": None,
        "experience_years": None,
        "career_length_years": None,
        "hall_of_fame_flag": 0,
        "hall_of_fame_role": None,
        "hall_of_fame_year": None,
        "hall_of_fame_raw": None,
        "headshot_url": extract_headshot_url(meta_html),
        "source_snapshot_fetched_at_utc": source_snapshot_fetched_at_utc,
        "_meta_source_key": source_key,
        "_meta_source_last_modified_utc": source_last_modified_utc,
    }
    for paragraph_html in PARAGRAPH_PATTERN.findall(meta_html):
        paragraph_text = null_if_empty(strip_tags(paragraph_html))
        if paragraph_text is None:
            continue
        raw_labels = detect_labels_in_paragraph(paragraph_html)
        labels = [label for label in (normalize_label_name(label) for label in raw_labels) if label is not None]
        if not labels:
            update_unlabeled_fields(row, paragraph_text)
            continue
        if labels == ["position", "shoots"]:
            row["position_raw"], row["shoots"] = parse_position_and_shoots(paragraph_text)
            continue
        first_label = labels[0]
        raw_label_text = raw_labels[0]
        value = parse_labeled_value(paragraph_text, raw_label_text)
        if first_label == "pronunciation":
            row["pronunciation"] = value
        elif first_label == "born":
            row.update(parse_birth_fields(paragraph_text, paragraph_html))
        elif first_label == "died":
            row["death_date"] = parse_attr_date_from_html(paragraph_html, "death")
        elif first_label == "team":
            row["current_team_raw"] = value
        elif first_label == "relatives":
            row["relatives_raw"] = value
        elif first_label == "college":
            row["college_raw"] = value
        elif first_label == "colleges":
            row["colleges_raw"] = value
        elif first_label == "high_school":
            row["high_school_raw"] = value
        elif first_label == "high_schools":
            row["high_schools_raw"] = value
        elif first_label == "recruiting_rank":
            row["recruiting_rank_raw"] = value
            row["recruiting_rank_year"], row["recruiting_rank_ordinal"] = parse_recruiting_rank(value)
        elif first_label == "draft":
            row["draft_raw"] = value
            row.update(parse_draft(value))
        elif first_label == "nba_debut":
            row["nba_debut_date"] = parse_visible_date_from_html(paragraph_html)
        elif first_label == "aba_debut":
            row["aba_debut_date"] = parse_visible_date_from_html(paragraph_html)
        elif first_label == "experience":
            row["experience_years"] = parse_experience_years(value)
        elif first_label == "career_length":
            row["career_length_years"] = parse_experience_years(value)
        elif first_label == "hall_of_fame":
            row["hall_of_fame_raw"] = value
            row["hall_of_fame_flag"], row["hall_of_fame_role"], row["hall_of_fame_year"] = parse_hall_of_fame(value)
    if row["formal_name"] is None:
        row["formal_name"] = row["page_player_name"]
    return row


def build_profile_artifacts(snapshots: list[RawHtmlSnapshot]) -> tuple[list[dict[str, Any]], int, Counter[str]]:
    rows: list[dict[str, Any]] = []
    parse_failures = 0
    warning_reason_counts: Counter[str] = Counter()
    for snapshot in snapshots:
        try:
            row = build_row(
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
        if row.get("player_profile_url") is None:
            warning_reason_counts["missing_player_profile_url"] += 1
        if row.get("page_player_name") is None:
            warning_reason_counts["missing_page_player_name"] += 1
        if row.get("birth_date") is None:
            warning_reason_counts["missing_birth_date"] += 1
        rows.append(row)
    if parse_failures > 0:
        warning_reason_counts["source_parse_failures"] = parse_failures
    return rows, parse_failures, warning_reason_counts
