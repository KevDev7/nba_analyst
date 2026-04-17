from __future__ import annotations

import io
import re
from datetime import date, datetime, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pyarrow as pa
import pyarrow.parquet as pq

S3_BUCKET = "nba-analytics-lakehouse-dev"

SEASON_TYPE_LABELS = {
    "001": "preseason",
    "002": "regular_season",
    "003": "all_star",
    "004": "playoffs",
    "005": "play_in",
    "006": "nba_cup_final",
}

TEAM_CONTEXT_BY_ID = {
    1610612737: {"conference": "east", "division": "southeast"},
    1610612738: {"conference": "east", "division": "atlantic"},
    1610612751: {"conference": "east", "division": "atlantic"},
    1610612766: {"conference": "east", "division": "southeast"},
    1610612741: {"conference": "east", "division": "central"},
    1610612739: {"conference": "east", "division": "central"},
    1610612765: {"conference": "east", "division": "central"},
    1610612754: {"conference": "east", "division": "central"},
    1610612748: {"conference": "east", "division": "southeast"},
    1610612749: {"conference": "east", "division": "central"},
    1610612752: {"conference": "east", "division": "atlantic"},
    1610612753: {"conference": "east", "division": "southeast"},
    1610612755: {"conference": "east", "division": "atlantic"},
    1610612761: {"conference": "east", "division": "atlantic"},
    1610612764: {"conference": "east", "division": "southeast"},
    1610612742: {"conference": "west", "division": "southwest"},
    1610612743: {"conference": "west", "division": "northwest"},
    1610612744: {"conference": "west", "division": "pacific"},
    1610612745: {"conference": "west", "division": "southwest"},
    1610612746: {"conference": "west", "division": "pacific"},
    1610612747: {"conference": "west", "division": "pacific"},
    1610612763: {"conference": "west", "division": "southwest"},
    1610612750: {"conference": "west", "division": "northwest"},
    1610612740: {"conference": "west", "division": "southwest"},
    1610612760: {"conference": "west", "division": "northwest"},
    1610612756: {"conference": "west", "division": "pacific"},
    1610612757: {"conference": "west", "division": "northwest"},
    1610612758: {"conference": "west", "division": "pacific"},
    1610612759: {"conference": "west", "division": "southwest"},
    1610612762: {"conference": "west", "division": "northwest"},
}

_ISO_DURATION_RE = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?$"
)


def null_if_empty(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def to_str_or_none(value: Any) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    return str(value).strip()


def to_int_or_none(value: Any) -> int | None:
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_positive_int_or_none(value: Any) -> int | None:
    parsed = to_int_or_none(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def to_float_or_none(value: Any) -> float | None:
    value = null_if_empty(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool_or_none(value: Any) -> bool | None:
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "t"}:
            return True
        if normalized in {"false", "0", "no", "n", "f"}:
            return False
    return None


def parse_timestamp_utc(value: Any) -> datetime | None:
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            parsed = value.replace(tzinfo=timezone.utc)
        else:
            parsed = value.astimezone(timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
    if parsed.year <= 1900:
        return None
    return parsed


def parse_date_or_none(value: Any) -> date | None:
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_game_code_date(value: Any) -> date | None:
    text = to_str_or_none(value)
    if text is None:
        return None
    prefix = text.split("/", 1)[0]
    if len(prefix) != 8 or not prefix.isdigit():
        return None
    try:
        return datetime.strptime(prefix, "%Y%m%d").date()
    except ValueError:
        return None


def normalize_game_id(value: Any) -> str | None:
    text = to_str_or_none(value)
    if text is None:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return text
    if len(digits) >= 10:
        return digits[-10:]
    return digits.zfill(10)


def season_type_code_from_game_id(value: Any) -> str | None:
    game_id = normalize_game_id(value)
    if game_id is None or len(game_id) < 3:
        return None
    return game_id[:3]


def season_type_label_from_code(value: Any) -> str | None:
    code = to_str_or_none(value)
    if code is None:
        return None
    return SEASON_TYPE_LABELS.get(code)


def season_start_year_from_label(value: Any) -> int | None:
    text = to_str_or_none(value)
    if text is None or len(text) < 4 or not text[:4].isdigit():
        return None
    return int(text[:4])


def season_year_label_from_start_year(value: Any) -> str | None:
    start_year = to_int_or_none(value)
    if start_year is None:
        return None
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def season_start_year_from_game_id(value: Any) -> int | None:
    game_id = normalize_game_id(value)
    if game_id is None or len(game_id) < 5 or not game_id[:5].isdigit():
        return None
    yy = int(game_id[3:5])
    return 2000 + yy if yy <= 50 else 1900 + yy


def season_year_from_game_id(value: Any) -> str | None:
    start_year = season_start_year_from_game_id(value)
    if start_year is None:
        return None
    return season_year_label_from_start_year(start_year)


def canonical_season_start_year_from_date(value: Any) -> int | None:
    event_date = parse_date_or_none(value)
    if event_date is None:
        return None
    return event_date.year if event_date.month >= 7 else event_date.year - 1


def canonical_season_year_from_date(value: Any) -> str | None:
    start_year = canonical_season_start_year_from_date(value)
    if start_year is None:
        return None
    return season_year_label_from_start_year(start_year)


def parse_iso_duration_seconds(value: Any) -> float | None:
    text = to_str_or_none(value)
    if text is None:
        return None
    match = _ISO_DURATION_RE.match(text)
    if not match:
        return None
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return hours * 3600 + minutes * 60 + seconds


def parse_iso_duration_minutes(value: Any) -> int | None:
    seconds = parse_iso_duration_seconds(value)
    if seconds is None:
        return None
    return int(round(seconds / 60))


def localized_date_from_timestamp(value: Any, timezone_name: Any) -> date | None:
    parsed = parse_timestamp_utc(value)
    if parsed is None:
        return None
    tz_name = to_str_or_none(timezone_name)
    if not tz_name:
        return parsed.date()
    try:
        return parsed.astimezone(ZoneInfo(tz_name)).date()
    except ZoneInfoNotFoundError:
        return parsed.date()


def normalize_position_group(value: Any) -> str:
    text = to_str_or_none(value)
    if text is None:
        return "unknown"
    normalized = text.upper().replace("-", "").replace("/", "").replace(" ", "")
    if normalized in {"PG", "SG", "G"}:
        return "guard"
    if normalized in {"SF", "PF", "F"}:
        return "forward"
    if normalized == "C":
        return "center"
    if normalized in {"GF", "FG"}:
        return "wing"
    if normalized in {"FC", "CF"}:
        return "big"
    if "G" in normalized and "F" in normalized:
        return "wing"
    if "F" in normalized and "C" in normalized:
        return "big"
    if "G" in normalized:
        return "guard"
    if "F" in normalized:
        return "forward"
    if "C" in normalized:
        return "center"
    return "unknown"


def safe_ratio(numerator: Any, denominator: Any) -> float | None:
    numerator_value = to_float_or_none(numerator)
    denominator_value = to_float_or_none(denominator)
    if numerator_value is None or denominator_value in {None, 0.0}:
        return None
    return numerator_value / denominator_value


def games_played_from_values(played: Any, seconds_played_total: Any) -> int:
    played_flag = to_int_or_none(played) == 1
    minutes_value = to_float_or_none(seconds_played_total) or 0.0
    return 1 if played_flag or minutes_value > 0 else 0


def choose_primary_team(records: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_key: tuple[int, int, int] | None = None

    for record in records:
        team_id = to_int_or_none(record.get("team_id"))
        if team_id is None:
            continue
        games_played = to_int_or_none(record.get("games_played")) or 0
        games_on_roster = to_int_or_none(record.get("games_on_roster")) or 0
        candidate_key = (games_played, games_on_roster, -team_id)
        if best_key is None or candidate_key > best_key:
            best = dict(record)
            best["team_id"] = team_id
            best_key = candidate_key

    return best


def team_context_for_id(team_id: Any) -> dict[str, str] | None:
    team_key = to_int_or_none(team_id)
    if team_key is None:
        return None
    return TEAM_CONTEXT_BY_ID.get(team_key)


def non_null_count(row: dict[str, Any], keys: Iterable[str]) -> int:
    return sum(1 for key in keys if row.get(key) is not None)


def best_row(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
    *,
    quality_keys: Iterable[str],
    preferred_timestamp_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    if current is None:
        return candidate
    for key in preferred_timestamp_keys or []:
        current_ts = current.get(key)
        candidate_ts = candidate.get(key)
        if current_ts is None and candidate_ts is not None:
            return candidate
        if current_ts is not None and candidate_ts is not None and candidate_ts > current_ts:
            return candidate
    if non_null_count(candidate, quality_keys) > non_null_count(current, quality_keys):
        return candidate
    return current


def read_parquet_table_from_s3(s3_client, key: str, required_columns: list[str]) -> pa.Table:
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload = response["Body"].read()
    schema = pq.read_schema(pa.BufferReader(payload))
    available_by_lower = {name.lower(): name for name in schema.names}
    selected_actual: list[str] = []
    selected_requested: list[str] = []
    for required_name in required_columns:
        actual_name = available_by_lower.get(required_name.lower())
        if actual_name is None:
            continue
        selected_actual.append(actual_name)
        selected_requested.append(required_name)
    if selected_actual:
        table = pq.read_table(pa.BufferReader(payload), columns=selected_actual)
        if selected_requested != selected_actual:
            table = table.rename_columns(selected_requested)
    else:
        table = pq.read_table(pa.BufferReader(payload))
        if table.num_columns > 0:
            table = table.select([])
    for missing in [col for col in required_columns if col not in selected_requested]:
        table = table.append_column(missing, pa.nulls(table.num_rows, type=pa.null()))
    return table.select(required_columns)


def write_parquet_to_s3(rows: list[dict[str, Any]], schema: pa.Schema, destination_key: str, s3_client) -> None:
    table = pa.Table.from_pylist(rows, schema=schema)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=destination_key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )
