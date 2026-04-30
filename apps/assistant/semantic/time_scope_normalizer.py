from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dateutil import parser as date_parser


@dataclass(frozen=True)
class NormalizedTimeWindow:
    kind: str
    value: str


_DATE_PHRASE = r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{2,4})?)"
_BETWEEN_RE = re.compile(
    rf"\bbetween\s+(?P<start>{_DATE_PHRASE})\s+(?:and|to|through)\s+(?P<end>{_DATE_PHRASE})",
    re.IGNORECASE,
)
_FROM_TO_RE = re.compile(
    rf"\bfrom\s+(?P<start>{_DATE_PHRASE})\s+(?:to|through|until)\s+(?P<end>{_DATE_PHRASE})",
    re.IGNORECASE,
)
_SINCE_RE = re.compile(rf"\bsince\s+(?P<date>{_DATE_PHRASE})", re.IGNORECASE)
_UNTIL_RE = re.compile(rf"\b(?:until|before|through)\s+(?P<date>{_DATE_PHRASE})", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{2,4}))\b")


def normalize_question_time_window(question: str) -> Optional[NormalizedTimeWindow]:
    # Convert explicit user-facing date phrases into the canonical time_window
    # shape Haskell already validates. Fuzzy/event dates intentionally do not parse.
    for pattern in (_BETWEEN_RE, _FROM_TO_RE):
        match = pattern.search(question)
        if match:
            return _normalize_range(match.group("start"), match.group("end"))

    since_match = _SINCE_RE.search(question)
    if since_match:
        start_date = _parse_explicit_date(since_match.group("date"), fallback_year=None)
        if start_date is not None:
            return NormalizedTimeWindow("since_date", start_date)

    until_match = _UNTIL_RE.search(question)
    if until_match:
        end_date = _parse_explicit_date(until_match.group("date"), fallback_year=None)
        if end_date is not None:
            return NormalizedTimeWindow("until_date", end_date)

    return None


def _normalize_range(raw_start: str, raw_end: str) -> Optional[NormalizedTimeWindow]:
    fallback_year = _explicit_year(raw_start) or _explicit_year(raw_end)
    start_date = _parse_explicit_date(raw_start, fallback_year=fallback_year)
    end_date = _parse_explicit_date(raw_end, fallback_year=fallback_year)
    if start_date is None or end_date is None:
        return None
    return NormalizedTimeWindow("between_dates", f"{start_date} to {end_date}")


def _parse_explicit_date(raw_value: str, *, fallback_year: int | None) -> Optional[str]:
    if _explicit_year(raw_value) is None and fallback_year is None:
        return None
    default_year = fallback_year or 2000
    try:
        parsed = date_parser.parse(
            _normalize_ordinal_suffixes(raw_value),
            default=datetime(default_year, 1, 1),
            dayfirst=False,
            fuzzy=False,
        )
    except (ValueError, OverflowError):
        return None
    return parsed.date().isoformat()


def _explicit_year(raw_value: str) -> Optional[int]:
    full_year_match = re.search(r"\b(20\d{2})\b", raw_value)
    if full_year_match:
        return int(full_year_match.group(1))

    short_slash_match = re.search(r"\b\d{1,2}/\d{1,2}/(\d{2})\b", raw_value)
    if short_slash_match:
        return 2000 + int(short_slash_match.group(1))

    short_text_match = re.search(r"\b[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+)(\d{2})\b", raw_value)
    if short_text_match:
        return 2000 + int(short_text_match.group(1))

    return None


def _normalize_ordinal_suffixes(raw_value: str) -> str:
    return re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", raw_value, flags=re.IGNORECASE)
