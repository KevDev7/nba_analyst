"""Build silver QA rows comparing reconstructed period starters to an independent reference.

Reference method:
  - period-range boxscore player presence gives every player who appeared in a period
  - the first substitution event for each player in that period indicates whether they began on court
  - players whose first substitution is IN are excluded from the period-starter set

Reads:
  s3://nba-analytics-lakehouse-dev/raw/boxscoretraditionalv3/period_player_stats/
  s3://nba-analytics-lakehouse-dev/silver/event_projection_v2/game_id=<GAME_ID>.parquet
  s3://nba-analytics-lakehouse-dev/silver/on_court_state/game_id=<GAME_ID>.parquet

Writes:
  s3://nba-analytics-lakehouse-dev/silver/on_court_period_starter_qa.parquet
"""

from __future__ import annotations

import io
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

from silver_pipeline_helpers import write_audit_artifacts, write_rows_as_parquet

load_dotenv(override=True)

S3_BUCKET = "nba-analytics-lakehouse-dev"
PERIOD_RANGE_PREFIX = "raw/boxscoretraditionalv3/period_player_stats/"
EVENT_PROJECTION_PREFIX = "silver/event_projection_v2/"
ON_COURT_PREFIX = "silver/on_court_state/"
DESTINATION_KEY = "silver/on_court_period_starter_qa.parquet"
TABLE_NAME = "on_court_period_starter_qa"
SOURCE_SYSTEM = "raw_boxscoretraditionalv3_period_player_stats|silver_event_projection_v2|silver_on_court_state"
META_SCHEMA_VERSION = 1

PERIOD_KEY_RE = re.compile(r"game_id=([0-9]+)/period=([0-9]+)\.json$")

EVENT_COLUMNS = [
    "game_id",
    "event_num",
    "event_order",
    "period",
    "is_substitution_event",
    "team_id",
    "player1_id",
    "sub_type",
]

ON_COURT_COLUMNS = [
    "gameId",
    "period",
    "stint_id",
    "start_orderNumber",
    "home_teamId",
    "away_teamId",
    "home_personIds",
    "away_personIds",
    "lineup_valid_flag",
    "lineup_issue",
]

TARGET_COLUMNS = [
    "gameId",
    "period",
    "team_side",
    "teamId",
    "current_starter_personIds",
    "reference_starter_personIds",
    "reference_period_personIds",
    "missing_from_current_personIds",
    "extra_in_current_personIds",
    "match_flag",
    "qa_status",
    "qa_issue",
    "current_lineup_valid_flag",
    "current_lineup_issue",
    "reference_source_method",
]

META_COLUMNS = [
    "_meta_pipeline_run_id",
    "_meta_ingested_at_utc",
    "_meta_source_system",
    "_meta_source_key",
    "_meta_source_last_modified_utc",
    "_meta_schema_version",
]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("gameId", pa.string()),
        pa.field("period", pa.int64()),
        pa.field("team_side", pa.string()),
        pa.field("teamId", pa.int64()),
        pa.field("current_starter_personIds", pa.list_(pa.int64())),
        pa.field("reference_starter_personIds", pa.list_(pa.int64())),
        pa.field("reference_period_personIds", pa.list_(pa.int64())),
        pa.field("missing_from_current_personIds", pa.list_(pa.int64())),
        pa.field("extra_in_current_personIds", pa.list_(pa.int64())),
        pa.field("match_flag", pa.int64()),
        pa.field("qa_status", pa.string()),
        pa.field("qa_issue", pa.string()),
        pa.field("current_lineup_valid_flag", pa.int64()),
        pa.field("current_lineup_issue", pa.string()),
        pa.field("reference_source_method", pa.string()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def null_if_empty(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


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


def normalize_game_id(value: Any) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(10) if digits else None


def sorted_unique_ints(values: Any) -> list[int]:
    if values is None:
        return []
    if hasattr(values, "tolist"):
        values = values.tolist()
    if not isinstance(values, list):
        values = [values]
    normalized = [to_int_or_none(value) for value in values]
    return sorted({value for value in normalized if value is not None})


def normalize_text(value: Any) -> str | None:
    value = null_if_empty(value)
    if value is None:
        return None
    return str(value).strip().lower().replace(" ", "").replace("_", "")


def parse_duration_seconds(value: Any) -> float | None:
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    iso_match = re.fullmatch(
        r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?",
        text,
    )
    if iso_match:
        hours = float(iso_match.group("hours") or 0)
        minutes = float(iso_match.group("minutes") or 0)
        seconds = float(iso_match.group("seconds") or 0)
        return hours * 3600 + minutes * 60 + seconds
    clock_match = re.fullmatch(r"(?P<minutes>\d+):(?P<seconds>\d+(?:\.\d+)?)", text)
    if clock_match:
        return float(clock_match.group("minutes")) * 60 + float(clock_match.group("seconds"))
    return None


def player_has_period_presence(player: dict[str, Any]) -> bool:
    stats = player.get("statistics") if isinstance(player.get("statistics"), dict) else {}
    candidates = [player, stats]
    saw_duration = False
    for candidate in candidates:
        for key in ("minutesCalculated", "minutes", "MIN"):
            seconds = parse_duration_seconds(candidate.get(key))
            if seconds is not None:
                saw_duration = True
                if seconds > 0:
                    return True
    stat_keys = [
        "points",
        "assists",
        "reboundsTotal",
        "reboundsOffensive",
        "reboundsDefensive",
        "fieldGoalsAttempted",
        "fieldGoalsMade",
        "freeThrowsAttempted",
        "freeThrowsMade",
        "threePointersAttempted",
        "threePointersMade",
        "turnovers",
        "steals",
        "blocks",
    ]
    has_positive_stat = any(
        (to_int_or_none(candidate.get(key)) or 0) > 0
        for candidate in candidates
        for key in stat_keys
    )
    if has_positive_stat:
        return True
    return False if saw_duration else False


def team_objects_from_payload(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    for root in (payload.get("boxScoreTraditional"), payload.get("game"), payload):
        if not isinstance(root, dict):
            continue
        home = root.get("homeTeam")
        away = root.get("awayTeam")
        if isinstance(home, dict) and isinstance(away, dict):
            return [("home", home), ("away", away)]
    return []


def extract_period_presence_rows(
    payload: dict[str, Any],
    *,
    fallback_game_id: str | None,
    period: int,
) -> list[dict[str, Any]]:
    game_id = normalize_game_id(
        payload.get("gameId")
        or (payload.get("game") or {}).get("gameId")
        or (payload.get("boxScoreTraditional") or {}).get("gameId")
        or fallback_game_id
    )
    rows: list[dict[str, Any]] = []
    for team_side, team in team_objects_from_payload(payload):
        team_id = to_int_or_none(team.get("teamId"))
        for player in team.get("players") or []:
            if not isinstance(player, dict) or not player_has_period_presence(player):
                continue
            person_id = to_int_or_none(player.get("personId") or player.get("PLAYER_ID"))
            if game_id is None or team_id is None or person_id is None:
                continue
            rows.append(
                {
                    "gameId": game_id,
                    "period": period,
                    "team_side": team_side,
                    "teamId": team_id,
                    "personId": person_id,
                }
            )
    return rows


def first_sub_direction_by_player(event_rows: list[dict[str, Any]]) -> dict[tuple[int, int, int], str]:
    first_by_key: dict[tuple[int, int, int], tuple[int, int, str]] = {}
    for row in event_rows:
        if not bool(row.get("is_substitution_event")):
            continue
        period = to_int_or_none(row.get("period"))
        team_id = to_int_or_none(row.get("team_id"))
        person_id = to_int_or_none(row.get("player1_id"))
        direction = normalize_text(row.get("sub_type"))
        if period is None or team_id is None or person_id is None or direction not in {"in", "out"}:
            continue
        sort_key = (
            to_int_or_none(row.get("event_order")) or 0,
            to_int_or_none(row.get("event_num")) or 0,
            direction,
        )
        key = (period, team_id, person_id)
        existing = first_by_key.get(key)
        if existing is None or sort_key < existing:
            first_by_key[key] = sort_key
    return {key: direction for key, (_, _, direction) in first_by_key.items()}


def derive_reference_starters(
    period_player_ids: list[int],
    *,
    period: int,
    team_id: int,
    event_rows: list[dict[str, Any]],
) -> list[int]:
    player_ids = sorted_unique_ints(period_player_ids)
    first_subs = first_sub_direction_by_player(event_rows)
    subbed_in = {
        person_id
        for person_id in player_ids
        if first_subs.get((period, team_id, person_id)) == "in"
    }
    return sorted(player_id for player_id in player_ids if player_id not in subbed_in)


def first_current_stint_by_period_team(on_court_rows: list[dict[str, Any]]) -> dict[tuple[int, str], dict[str, Any]]:
    ordered = sorted(
        on_court_rows,
        key=lambda row: (
            to_int_or_none(row.get("period")) or 0,
            to_int_or_none(row.get("start_orderNumber")) or 0,
            to_int_or_none(row.get("stint_id")) or 0,
        ),
    )
    result: dict[tuple[int, str], dict[str, Any]] = {}
    for row in ordered:
        period = to_int_or_none(row.get("period"))
        if period is None:
            continue
        for team_side in ("home", "away"):
            result.setdefault((period, team_side), row)
    return result


def build_qa_rows_for_game(
    *,
    game_id: str,
    period_presence_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]],
    on_court_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    period_players: dict[tuple[int, str, int], list[int]] = {}
    for row in period_presence_rows:
        period = to_int_or_none(row.get("period"))
        team_side = null_if_empty(row.get("team_side"))
        team_id = to_int_or_none(row.get("teamId"))
        person_id = to_int_or_none(row.get("personId"))
        if period is None or team_side not in {"home", "away"} or team_id is None or person_id is None:
            continue
        period_players.setdefault((period, str(team_side), team_id), []).append(person_id)

    current_by_period_team = first_current_stint_by_period_team(on_court_rows)
    rows: list[dict[str, Any]] = []
    for (period, team_side, team_id), player_ids in sorted(period_players.items()):
        current_stint = current_by_period_team.get((period, team_side))
        current_players = (
            sorted_unique_ints(current_stint.get(f"{team_side}_personIds"))
            if current_stint is not None
            else []
        )
        reference_period_players = sorted_unique_ints(player_ids)
        reference_starters = derive_reference_starters(
            reference_period_players,
            period=period,
            team_id=team_id,
            event_rows=event_rows,
        )
        missing_from_current = sorted(set(reference_starters) - set(current_players))
        extra_in_current = sorted(set(current_players) - set(reference_starters))
        current_valid_flag = (
            to_int_or_none(current_stint.get("lineup_valid_flag"))
            if current_stint is not None
            else None
        )
        current_issue = (
            null_if_empty(current_stint.get("lineup_issue"))
            if current_stint is not None
            else "missing_current_period_stint"
        )

        qa_status = "match"
        qa_issue = None
        match_flag = 1
        if current_stint is None:
            qa_status = "missing_current"
            qa_issue = "missing_current_period_stint"
            match_flag = 0
        elif current_valid_flag != 1 or len(current_players) != 5:
            qa_status = "invalid_current"
            qa_issue = current_issue or "current_period_stint_not_valid_five"
            match_flag = 0
        elif len(reference_starters) != 5:
            qa_status = "incomplete_reference"
            qa_issue = f"reference_starter_count={len(reference_starters)}"
            match_flag = 0
        elif missing_from_current or extra_in_current:
            qa_status = "mismatch"
            qa_issue = "starter_sets_differ"
            match_flag = 0

        rows.append(
            {
                "gameId": game_id,
                "period": period,
                "team_side": team_side,
                "teamId": team_id,
                "current_starter_personIds": current_players,
                "reference_starter_personIds": reference_starters,
                "reference_period_personIds": reference_period_players,
                "missing_from_current_personIds": missing_from_current,
                "extra_in_current_personIds": extra_in_current,
                "match_flag": match_flag,
                "qa_status": qa_status,
                "qa_issue": qa_issue,
                "current_lineup_valid_flag": current_valid_flag,
                "current_lineup_issue": current_issue,
                "reference_source_method": "period_range_boxscore_minus_first_sub_in",
            }
        )
    return rows


def extract_game_period_from_period_key(key: str) -> tuple[str, int] | None:
    match = PERIOD_KEY_RE.search(key)
    if match is None:
        return None
    return match.group(1).zfill(10), int(match.group(2))


def list_objects(s3_client, prefix: str, suffix: str) -> list[dict[str, Any]]:
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(suffix):
                objects.append(obj)
    return objects


def key_by_game(prefix: str, objects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for obj in objects:
        key = obj.get("Key", "")
        match = re.search(r"game_id=([0-9]+)\.parquet$", key)
        if match is not None:
            result[match.group(1).zfill(10)] = obj
    return result


def read_json(s3_client, key: str) -> dict[str, Any]:
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    return json.loads(response["Body"].read().decode("utf-8"))


def read_parquet_rows(s3_client, key: str, columns: list[str]) -> list[dict[str, Any]]:
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    table = pq.read_table(io.BytesIO(response["Body"].read()), columns=columns)
    return table.to_pylist()


def add_metadata(rows: list[dict[str, Any]], *, pipeline_run_id: str, ingested_at_utc: datetime, source_key: str, source_last_modified_utc: datetime | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        enriched = dict(row)
        enriched["_meta_pipeline_run_id"] = pipeline_run_id
        enriched["_meta_ingested_at_utc"] = ingested_at_utc
        enriched["_meta_source_system"] = SOURCE_SYSTEM
        enriched["_meta_source_key"] = source_key
        enriched["_meta_source_last_modified_utc"] = source_last_modified_utc
        enriched["_meta_schema_version"] = META_SCHEMA_VERSION
        output.append(enriched)
    return output


def main() -> None:
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"{TABLE_NAME}_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"

    period_objects = list_objects(s3_client, PERIOD_RANGE_PREFIX, ".json")
    event_objects = key_by_game(EVENT_PROJECTION_PREFIX, list_objects(s3_client, EVENT_PROJECTION_PREFIX, ".parquet"))
    on_court_objects = key_by_game(ON_COURT_PREFIX, list_objects(s3_client, ON_COURT_PREFIX, ".parquet"))

    period_objects_by_game: dict[str, list[dict[str, Any]]] = {}
    for obj in period_objects:
        parsed = extract_game_period_from_period_key(obj.get("Key", ""))
        if parsed is None:
            continue
        period_objects_by_game.setdefault(parsed[0], []).append(obj)

    selected_game_ids = sorted(set(period_objects_by_game) & set(event_objects) & set(on_court_objects))
    output_rows: list[dict[str, Any]] = []
    skipped_games: list[str] = []
    qa_status_counts: Counter[str] = Counter()

    for index, game_id in enumerate(selected_game_ids, start=1):
        try:
            period_presence_rows: list[dict[str, Any]] = []
            source_keys: list[str] = []
            source_last_modified_values: list[datetime] = []
            for obj in sorted(period_objects_by_game[game_id], key=lambda item: item.get("Key", "")):
                key = obj.get("Key", "")
                parsed = extract_game_period_from_period_key(key)
                if parsed is None:
                    continue
                _, period = parsed
                payload = read_json(s3_client, key)
                period_presence_rows.extend(
                    extract_period_presence_rows(payload, fallback_game_id=game_id, period=period)
                )
                source_keys.append(key)
                last_modified = obj.get("LastModified")
                if isinstance(last_modified, datetime):
                    source_last_modified_values.append(last_modified.astimezone(timezone.utc))

            event_key = event_objects[game_id]["Key"]
            on_court_key = on_court_objects[game_id]["Key"]
            event_rows = read_parquet_rows(s3_client, event_key, EVENT_COLUMNS)
            on_court_rows = read_parquet_rows(s3_client, on_court_key, ON_COURT_COLUMNS)
            game_rows = build_qa_rows_for_game(
                game_id=game_id,
                period_presence_rows=period_presence_rows,
                event_rows=event_rows,
                on_court_rows=on_court_rows,
            )
            source_keys.extend([event_key, on_court_key])
            source_last_modified = max(source_last_modified_values) if source_last_modified_values else None
            source_key = json.dumps(source_keys, sort_keys=True)
            output_rows.extend(
                add_metadata(
                    game_rows,
                    pipeline_run_id=pipeline_run_id,
                    ingested_at_utc=ingested_at_utc,
                    source_key=source_key,
                    source_last_modified_utc=source_last_modified,
                )
            )
            qa_status_counts.update(row["qa_status"] for row in game_rows)
            print(f"[{index}/{len(selected_game_ids)}] Completed game_id={game_id} qa_rows={len(game_rows)}")
        except Exception as exc:  # noqa: BLE001
            skipped_games.append(game_id)
            print(f"[{index}/{len(selected_game_ids)}] Skipping game_id={game_id}: {type(exc).__name__}: {exc}")

    write_rows_as_parquet(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        key=DESTINATION_KEY,
        rows=output_rows,
        schema=TARGET_SCHEMA,
    )

    warning_reason_counts = {
        key: value
        for key, value in sorted(qa_status_counts.items())
        if key != "match"
    }
    if skipped_games:
        warning_reason_counts["skipped_games"] = len(skipped_games)
    warning_count = sum(warning_reason_counts.values())
    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": "success_with_warnings" if warning_count else "success",
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "period_range_prefix": PERIOD_RANGE_PREFIX,
        "event_projection_prefix": EVENT_PROJECTION_PREFIX,
        "on_court_prefix": ON_COURT_PREFIX,
        "destination_key": DESTINATION_KEY,
        "period_range_file_count": len(period_objects),
        "selected_game_count": len(selected_game_ids),
        "output_row_count": len(output_rows),
        "qa_status_counts": json.dumps(dict(sorted(qa_status_counts.items())), sort_keys=True),
        "skipped_game_ids": json.dumps(skipped_games[:1000], sort_keys=True),
        "warning_count": warning_count,
        "error_count": 0,
        "warning_reason_counts": json.dumps(warning_reason_counts, sort_keys=True),
        "error_reason_counts": "{}",
    }
    audit_json_key, audit_parquet_key = write_audit_artifacts(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        audit_row=audit_row,
    )
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")
    print(f"Wrote audit JSON: s3://{S3_BUCKET}/{audit_json_key}")
    print(f"Wrote audit parquet: s3://{S3_BUCKET}/{audit_parquet_key}")


if __name__ == "__main__":
    main()
