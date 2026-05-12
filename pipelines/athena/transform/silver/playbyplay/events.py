"""
Transform raw CDN play-by-play JSON files into per-game silver parquet files.

Source:
  s3://nba-analytics-lakehouse-dev/raw/cdn/playbyplay/

Destination (upsert by game_id):
  s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=<GAME_ID>.parquet
"""

from __future__ import annotations

import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from heavy_silver_runtime import (
    build_source_index_from_objects,
    checkpoint_rows_with_updates,
    datetime_to_iso,
    normalize_utc_datetime,
    parse_target_game_ids,
    read_checkpoint_index,
    read_json_state,
    select_game_ids_for_processing,
    write_checkpoint_index,
    write_json_state,
)
from silver_pipeline_helpers import run_date, write_audit_artifacts

try:
    from incremental_state import (
        parse_state_datetime as shared_parse_state_datetime,
        select_incremental_game_ids_from_watermark_state,
        state_datetime_to_iso as shared_state_datetime_to_iso,
    )
except ModuleNotFoundError:
    from pipelines.athena.transform.silver.incremental_state import (
        parse_state_datetime as shared_parse_state_datetime,
        select_incremental_game_ids_from_watermark_state,
        state_datetime_to_iso as shared_state_datetime_to_iso,
    )

load_dotenv(override=True)  # Ensure .env credentials override any system variables

S3_BUCKET = "nba-analytics-lakehouse-dev"
SOURCE_PREFIX = "raw/cdn/playbyplay/"
BOXSCORE_PREFIX = "raw/cdn/boxscore/"
DESTINATION_PREFIX = "silver/playbyplay/"
TABLE_NAME = "playbyplay_events"
STATE_KEY = "silver/_state/playbyplay_events_state.json"
META_SOURCE_SYSTEM = "nba_cdn_playbyplay"
META_SCHEMA_VERSION = 1
CDN_BOXSCORE_URL_TEMPLATE = (
    "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
)
CDN_REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.nba.com",
    "Referer": "https://www.nba.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}
CDN_REQUEST_TIMEOUT_SECONDS = 25

# Run mode:
# - True: process all raw play-by-play files under SOURCE_PREFIX
# - False: process only TARGET_SOURCE_S3_PATH
PROCESS_ALL_FILES = os.getenv("PLAYBYPLAY_PROCESS_ALL_FILES", "true").strip().lower() != "false"
INCREMENTAL_MODE = os.getenv("PLAYBYPLAY_INCREMENTAL_MODE", "true").strip().lower() != "false"
FORCE_FULL_REFRESH = os.getenv("PLAYBYPLAY_FORCE_FULL_REFRESH", "false").strip().lower() == "true"
INCREMENTAL_LOOKBACK_MINUTES = 60
TARGET_GAME_IDS = parse_target_game_ids(os.getenv("PLAYBYPLAY_TARGET_GAME_IDS", ""))

# Used only when PROCESS_ALL_FILES = False
TARGET_SOURCE_S3_PATH = os.getenv(
    "PLAYBYPLAY_TARGET_SOURCE_S3_PATH",
    "s3://nba-analytics-lakehouse-dev/raw/cdn/playbyplay/game_id=22000517.json",
)
ATHENA_DIR = next(parent for parent in Path(__file__).resolve().parents if parent.name == "athena")
PERIOD_START_OVERRIDE_FILE = ATHENA_DIR / "metadata" / "playbyplay_period_start_overrides.json"

ACTION_COLUMNS = [
    "gameDateTimeEst",
    "actionNumber",
    "actionType",
    "prevActionNumber",
    "nextActionNumber",
    "area",
    "areaDetail",
    "assistPersonId",
    "assistFullName",
    "assistPlayerName",
    "assistPlayerNameInitial",
    "assistTotal",
    "blockPersonId",
    "blockFullName",
    "blockPlayerName",
    "clock",
    "description",
    "descriptor",
    "edited",
    "foulDrawnPersonId",
    "foulDrawnFullName",
    "foulDrawnPlayerName",
    "foulPersonalTotal",
    "foulTechnicalTotal",
    "isFieldGoal",
    "isTargetScoreLastPeriod",
    "jerseyNumber",
    "location",
    "jumpBallLostFullName",
    "jumpBallLostPersonId",
    "jumpBallLostPlayerName",
    "jumpBallRecoveredFullName",
    "jumpBallRecoveredName",
    "jumpBallRecoveredPersonId",
    "jumpBallWonFullName",
    "jumpBallWonPersonId",
    "jumpBallWonPlayerName",
    "officialId",
    "orderNumber",
    "prevOrderNumber",
    "nextOrderNumber",
    "period",
    "periodType",
    "personId",
    "personIdsFilter",
    "playerFullName",
    "playerName",
    "playerNameI",
    "playerteamCity",
    "playerteamName",
    "pointsTotal",
    "opponentteamCity",
    "opponentteamName",
    "possession",
    "qualifiers",
    "reboundDefensiveTotal",
    "reboundOffensiveTotal",
    "reboundTotal",
    "scoreAway",
    "scoreHome",
    "scoreMarginBefore",
    "scoreMarginAfter",
    "shortFormattedClock",
    "shotActionNumber",
    "shotDistance",
    "shotResult",
    "shotValue",
    "side",
    "resolvedOffenseTeamId",
    "resolvedDefenseTeamId",
    "offenseHomeAway",
    "defenseHomeAway",
    "secondsRemainingInPeriod",
    "secondsSincePreviousEvent",
    "stealPersonId",
    "stealFullName",
    "stealPlayerName",
    "stealTotal",
    "subType",
    "subsInFullName",
    "subsInPersonId",
    "subsInPlayerName",
    "teamId",
    "teamTricode",
    "timeActual",
    "turnoverTotal",
    "value",
    "x",
    "xLegacy",
    "y",
    "yLegacy",
    "isMadeShot",
    "isMissedShot",
    "isFreeThrow",
    "isRebound",
    "isTurnover",
    "isFoul",
    "isSubstitution",
    "isTimeout",
    "isJumpBall",
    "isPossessionEndingEvent",
    "countAsPossession",
    "possessionBoundaryReason",
    "foulsToGiveOffense",
    "foulsToGiveDefense",
    "isSecondChanceEvent",
    "isPenaltyEvent",
    "isOreb",
    "isDreb",
    "inferredReboundType",
    "reboundTypeSourceMismatchFlag",
    "isPlaceholderRebound",
    "isShootingFoul",
    "isTechnicalFt",
    "isFlagrantFt",
    "isBadPassTurnover",
    "isLostBallTurnover",
    "isTravelTurnover",
    "isShotClockTurnover",
    "teamStartingPeriodWithBall",
    "isPeriodStartEvent",
    "isPeriodEndEvent",
    "linkedShotActionNumber",
    "reboundOfMissedShotFlag",
    "freeThrowTripSequenceNum",
    "freeThrowTripSize",
]

INT_FIELDS = {
    "actionNumber",
    "assistPersonId",
    "assistTotal",
    "blockPersonId",
    "foulDrawnPersonId",
    "foulPersonalTotal",
    "foulTechnicalTotal",
    "isFieldGoal",
    "jumpBallLostPersonId",
    "jumpBallRecoveredPersonId",
    "jumpBallWonPersonId",
    "nextActionNumber",
    "nextOrderNumber",
    "officialId",
    "orderNumber",
    "period",
    "personId",
    "pointsTotal",
    "possession",
    "reboundDefensiveTotal",
    "reboundOffensiveTotal",
    "reboundTotal",
    "scoreAway",
    "scoreHome",
    "prevActionNumber",
    "prevOrderNumber",
    "shotActionNumber",
    "shotValue",
    "scoreMarginAfter",
    "scoreMarginBefore",
    "resolvedDefenseTeamId",
    "resolvedOffenseTeamId",
    "stealPersonId",
    "stealTotal",
    "subsInPersonId",
    "teamId",
    "turnoverTotal",
    "foulsToGiveOffense",
    "foulsToGiveDefense",
    "teamStartingPeriodWithBall",
    "linkedShotActionNumber",
    "freeThrowTripSequenceNum",
    "freeThrowTripSize",
}

FLOAT_FIELDS = {
    "secondsRemainingInPeriod",
    "secondsSincePreviousEvent",
    "shotDistance",
    "x",
    "xLegacy",
    "y",
    "yLegacy",
}
BOOL_FIELDS = {
    "isFoul",
    "isFreeThrow",
    "isJumpBall",
    "isMadeShot",
    "isMissedShot",
    "isRebound",
    "isSubstitution",
    "isTargetScoreLastPeriod",
    "isTimeout",
    "isTurnover",
    "countAsPossession",
    "isPossessionEndingEvent",
    "isSecondChanceEvent",
    "isPenaltyEvent",
    "isOreb",
    "isDreb",
    "reboundTypeSourceMismatchFlag",
    "isPlaceholderRebound",
    "isShootingFoul",
    "isTechnicalFt",
    "isFlagrantFt",
    "isBadPassTurnover",
    "isLostBallTurnover",
    "isTravelTurnover",
    "isShotClockTurnover",
    "isPeriodStartEvent",
    "isPeriodEndEvent",
    "reboundOfMissedShotFlag",
}

TARGET_SCHEMA = pa.schema(
    [
        pa.field("gameId", pa.string()),
        pa.field("gameDateTimeEst", pa.string()),
        pa.field("actionNumber", pa.int64()),
        pa.field("actionType", pa.string()),
        pa.field("prevActionNumber", pa.int64()),
        pa.field("nextActionNumber", pa.int64()),
        pa.field("area", pa.string()),
        pa.field("areaDetail", pa.string()),
        pa.field("assistPersonId", pa.int64()),
        pa.field("assistFullName", pa.string()),
        pa.field("assistPlayerName", pa.string()),
        pa.field("assistPlayerNameInitial", pa.string()),
        pa.field("assistTotal", pa.int64()),
        pa.field("blockPersonId", pa.int64()),
        pa.field("blockFullName", pa.string()),
        pa.field("blockPlayerName", pa.string()),
        pa.field("clock", pa.string()),
        pa.field("description", pa.string()),
        pa.field("descriptor", pa.string()),
        pa.field("edited", pa.string()),
        pa.field("foulDrawnPersonId", pa.int64()),
        pa.field("foulDrawnFullName", pa.string()),
        pa.field("foulDrawnPlayerName", pa.string()),
        pa.field("foulPersonalTotal", pa.int64()),
        pa.field("foulTechnicalTotal", pa.int64()),
        pa.field("isFieldGoal", pa.int64()),
        pa.field("isTargetScoreLastPeriod", pa.bool_()),
        pa.field("jerseyNumber", pa.string()),
        pa.field("location", pa.string()),
        pa.field("jumpBallLostFullName", pa.string()),
        pa.field("jumpBallLostPersonId", pa.int64()),
        pa.field("jumpBallLostPlayerName", pa.string()),
        pa.field("jumpBallRecoveredFullName", pa.string()),
        pa.field("jumpBallRecoveredName", pa.string()),
        pa.field("jumpBallRecoveredPersonId", pa.int64()),
        pa.field("jumpBallWonFullName", pa.string()),
        pa.field("jumpBallWonPersonId", pa.int64()),
        pa.field("jumpBallWonPlayerName", pa.string()),
        pa.field("officialId", pa.int64()),
        pa.field("orderNumber", pa.int64()),
        pa.field("prevOrderNumber", pa.int64()),
        pa.field("nextOrderNumber", pa.int64()),
        pa.field("period", pa.int64()),
        pa.field("periodType", pa.string()),
        pa.field("personId", pa.int64()),
        pa.field("personIdsFilter", pa.list_(pa.int64())),
        pa.field("playerFullName", pa.string()),
        pa.field("playerName", pa.string()),
        pa.field("playerNameI", pa.string()),
        pa.field("playerteamCity", pa.string()),
        pa.field("playerteamName", pa.string()),
        pa.field("pointsTotal", pa.int64()),
        pa.field("opponentteamCity", pa.string()),
        pa.field("opponentteamName", pa.string()),
        pa.field("possession", pa.int64()),
        pa.field("qualifiers", pa.list_(pa.string())),
        pa.field("reboundDefensiveTotal", pa.int64()),
        pa.field("reboundOffensiveTotal", pa.int64()),
        pa.field("reboundTotal", pa.int64()),
        pa.field("scoreAway", pa.int64()),
        pa.field("scoreHome", pa.int64()),
        pa.field("scoreMarginBefore", pa.int64()),
        pa.field("scoreMarginAfter", pa.int64()),
        pa.field("shortFormattedClock", pa.string()),
        pa.field("shotActionNumber", pa.int64()),
        pa.field("shotDistance", pa.float64()),
        pa.field("shotResult", pa.string()),
        pa.field("shotValue", pa.int64()),
        pa.field("side", pa.string()),
        pa.field("resolvedOffenseTeamId", pa.int64()),
        pa.field("resolvedDefenseTeamId", pa.int64()),
        pa.field("offenseHomeAway", pa.string()),
        pa.field("defenseHomeAway", pa.string()),
        pa.field("secondsRemainingInPeriod", pa.float64()),
        pa.field("secondsSincePreviousEvent", pa.float64()),
        pa.field("stealPersonId", pa.int64()),
        pa.field("stealFullName", pa.string()),
        pa.field("stealPlayerName", pa.string()),
        pa.field("stealTotal", pa.int64()),
        pa.field("subType", pa.string()),
        pa.field("subsInFullName", pa.string()),
        pa.field("subsInPersonId", pa.int64()),
        pa.field("subsInPlayerName", pa.string()),
        pa.field("teamId", pa.int64()),
        pa.field("teamTricode", pa.string()),
        pa.field("timeActual", pa.string()),
        pa.field("turnoverTotal", pa.int64()),
        pa.field("value", pa.string()),
        pa.field("x", pa.float64()),
        pa.field("xLegacy", pa.float64()),
        pa.field("y", pa.float64()),
        pa.field("yLegacy", pa.float64()),
        pa.field("isMadeShot", pa.bool_()),
        pa.field("isMissedShot", pa.bool_()),
        pa.field("isFreeThrow", pa.bool_()),
        pa.field("isRebound", pa.bool_()),
        pa.field("isTurnover", pa.bool_()),
        pa.field("isFoul", pa.bool_()),
        pa.field("isSubstitution", pa.bool_()),
        pa.field("isTimeout", pa.bool_()),
        pa.field("isJumpBall", pa.bool_()),
        pa.field("isPossessionEndingEvent", pa.bool_()),
        pa.field("countAsPossession", pa.bool_()),
        pa.field("possessionBoundaryReason", pa.string()),
        pa.field("foulsToGiveOffense", pa.int64()),
        pa.field("foulsToGiveDefense", pa.int64()),
        pa.field("isSecondChanceEvent", pa.bool_()),
        pa.field("isPenaltyEvent", pa.bool_()),
        pa.field("isOreb", pa.bool_()),
        pa.field("isDreb", pa.bool_()),
        pa.field("inferredReboundType", pa.string()),
        pa.field("reboundTypeSourceMismatchFlag", pa.bool_()),
        pa.field("isPlaceholderRebound", pa.bool_()),
        pa.field("isShootingFoul", pa.bool_()),
        pa.field("isTechnicalFt", pa.bool_()),
        pa.field("isFlagrantFt", pa.bool_()),
        pa.field("isBadPassTurnover", pa.bool_()),
        pa.field("isLostBallTurnover", pa.bool_()),
        pa.field("isTravelTurnover", pa.bool_()),
        pa.field("isShotClockTurnover", pa.bool_()),
        pa.field("teamStartingPeriodWithBall", pa.int64()),
        pa.field("isPeriodStartEvent", pa.bool_()),
        pa.field("isPeriodEndEvent", pa.bool_()),
        pa.field("linkedShotActionNumber", pa.int64()),
        pa.field("reboundOfMissedShotFlag", pa.bool_()),
        pa.field("freeThrowTripSequenceNum", pa.int64()),
        pa.field("freeThrowTripSize", pa.int64()),
        pa.field("_meta_pipeline_run_id", pa.string()),
        pa.field("_meta_ingested_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_source_system", pa.string()),
        pa.field("_meta_source_key", pa.string()),
        pa.field("_meta_source_last_modified_utc", pa.timestamp("us", tz="UTC")),
        pa.field("_meta_schema_version", pa.int64()),
    ]
)


def write_details_json(
    s3_client,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    details: dict[str, Any],
) -> str:
    """Write detailed run diagnostics payload for skipped files."""
    key = (
        f"silver/_audit/{TABLE_NAME}/"
        f"run_date={run_date(ingested_at_utc)}/{pipeline_run_id}_details.json"
    )
    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(details, default=str, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )
    return key


def load_period_start_overrides() -> dict[str, Any]:
    """Load optional period-start offense overrides from repo metadata."""
    try:
        if not PERIOD_START_OVERRIDE_FILE.is_file():
            return {}
        return json.loads(PERIOD_START_OVERRIDE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


PERIOD_START_OVERRIDES = load_period_start_overrides()


def null_if_empty(value: Any) -> Any:
    """Convert empty strings to None."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def normalize_game_id(value: Any) -> str | None:
    """Return canonical 10-digit NBA game ids for numeric-like values."""
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d+", text):
        return text.zfill(10)
    return text or None


def normalize_name(value: Any) -> str | None:
    """Normalize player name for loose matching."""
    value = null_if_empty(value)
    if value is None:
        return None
    text = str(value).lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def to_int_or_none(value: Any) -> int | None:
    """Convert numeric-like values to int, else None for empty."""
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float_or_none(value: Any) -> float | None:
    """Convert numeric-like values to float, else None for empty."""
    value = null_if_empty(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool_or_none(value: Any) -> bool | None:
    """Convert common truthy/falsy values to bool."""
    value = null_if_empty(value)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def to_int_list_or_none(value: Any) -> list[int | None] | None:
    """Keep list shape and coerce items to ints when possible."""
    value = null_if_empty(value)
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    return [to_int_or_none(item) for item in value]


def to_str_list_or_none(value: Any) -> list[str | None] | None:
    """Keep list shape and coerce items to strings (empty -> None)."""
    value = null_if_empty(value)
    if value is None:
        return None
    if not isinstance(value, list):
        return None
    output: list[str | None] = []
    for item in value:
        item = null_if_empty(item)
        output.append(None if item is None else str(item))
    return output


def parse_clock_to_seconds_remaining(value: Any) -> float | None:
    """Parse live clock strings like PT11M23.40S into remaining seconds."""
    value = null_if_empty(value)
    if value is None:
        return None

    text = str(value).strip()
    iso_match = re.fullmatch(r"PT(?:(\d+)M)?([0-9]+(?:\.[0-9]+)?)S", text)
    if iso_match:
        minutes_text, seconds_text = iso_match.groups()
        minutes = int(minutes_text or "0")
        seconds = float(seconds_text)
        return minutes * 60 + seconds

    short_match = re.fullmatch(r"(\d+):(\d+(?:\.\d+)?)", text)
    if short_match:
        minutes_text, seconds_text = short_match.groups()
        return int(minutes_text) * 60 + float(seconds_text)

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def normalized_action_type(value: Any) -> str | None:
    """Normalize action type strings for semantic flag comparisons."""
    value = null_if_empty(value)
    if value is None:
        return None
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text or None


def derive_phase1_event_enrichments(action: dict[str, Any]) -> dict[str, Any]:
    """Return Phase 1 event-grain semantic flags for one raw action."""
    action_type = normalized_action_type(action.get("actionType"))
    is_field_goal = bool(to_int_or_none(action.get("isFieldGoal")))
    shot_result = null_if_empty(action.get("shotResult"))
    shot_result_normalized = None if shot_result is None else str(shot_result).strip().lower()

    return {
        "secondsRemainingInPeriod": parse_clock_to_seconds_remaining(action.get("clock")),
        "isMadeShot": is_field_goal and shot_result_normalized == "made",
        "isMissedShot": is_field_goal and shot_result_normalized == "missed",
        "isFreeThrow": action_type == "freethrow",
        "isRebound": action_type == "rebound",
        "isTurnover": action_type == "turnover",
        "isFoul": action_type == "foul",
        "isSubstitution": action_type == "substitution",
        "isTimeout": action_type == "timeout",
        "isJumpBall": action_type == "jumpball",
    }


def is_start_of_period_row(row: dict[str, Any]) -> bool:
    """Return True for explicit period-start marker rows."""
    action_type = normalized_action_type(row.get("actionType"))
    sub_type = normalized_action_type(row.get("subType"))
    return action_type == "period" and sub_type == "start"


def is_end_of_period_row(row: dict[str, Any]) -> bool:
    """Return True for explicit period-end marker rows."""
    action_type = normalized_action_type(row.get("actionType"))
    sub_type = normalized_action_type(row.get("subType"))
    return action_type == "period" and sub_type == "end"


def is_terminal_marker_row(row: dict[str, Any]) -> bool:
    """Return True for explicit period/game end marker rows."""
    action_type = normalized_action_type(row.get("actionType"))
    sub_type = normalized_action_type(row.get("subType"))
    return sub_type == "end" and action_type in {"period", "game"}


def is_non_technical_free_throw_row(row: dict[str, Any]) -> bool:
    """Return True when the row is a non-technical free throw."""
    if not row.get("isFreeThrow"):
        return False
    descriptor = normalized_action_type(row.get("descriptor"))
    return descriptor != "technical"


def score_pair_from_row(row: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """Return normalized home/away score tuple from a row."""
    if row is None:
        return None, None
    return to_int_or_none(row.get("scoreHome")), to_int_or_none(row.get("scoreAway"))


def score_margin_from_offense_team(
    offense_team_id: int | None,
    score_home: int | None,
    score_away: int | None,
    teams: dict[int, dict[str, Any]],
) -> int | None:
    """Return score margin from the perspective of the offense team."""
    if (
        offense_team_id is None
        or score_home is None
        or score_away is None
    ):
        return None
    team_meta = teams.get(offense_team_id) or {}
    location = team_meta.get("location")
    if location == "h":
        return score_home - score_away
    if location == "v":
        return score_away - score_home
    return None


def team_ids_from_boxscore_context(boxscore_context: dict[str, Any]) -> list[int]:
    """Return sorted team ids from boxscore context."""
    return sorted((boxscore_context.get("teams") or {}).keys())


def other_team_id(offense_team_id: int | None, team_ids: list[int]) -> int | None:
    """Return the non-offense team when exactly two teams are known."""
    if offense_team_id is None or len(team_ids) != 2 or offense_team_id not in team_ids:
        return None
    return team_ids[0] if team_ids[1] == offense_team_id else team_ids[1]


def period_start_override_team_id(game_id: Any, period: Any) -> int | None:
    """Return optional override for team starting the period with the ball."""
    normalized_game_id = null_if_empty(game_id)
    period_num = to_int_or_none(period)
    if normalized_game_id is None or period_num is None:
        return None
    game_overrides = PERIOD_START_OVERRIDES.get(str(normalized_game_id))
    if not isinstance(game_overrides, dict):
        return None
    return to_int_or_none(game_overrides.get(str(period_num)))


def team_starting_period_with_ball(rows: list[dict[str, Any]], index: int) -> int | None:
    """Infer which team starts a period with the ball using upcoming same-period actions."""
    row = rows[index]
    override_team_id = period_start_override_team_id(row.get("gameId"), row.get("period"))
    if override_team_id is not None:
        return override_team_id
    period = row.get("period")
    game_id = row.get("gameId")
    next_same_period_rows = [
        candidate
        for candidate in rows[index + 1 :]
        if candidate.get("gameId") == game_id and candidate.get("period") == period
    ]

    if not next_same_period_rows:
        return None

    period_num = to_int_or_none(period)
    first_next = next_same_period_rows[0]
    if (period_num == 1 or (period_num is not None and period_num >= 5)) and first_next.get("isJumpBall"):
        return to_int_or_none(first_next.get("teamId"))

    for candidate in next_same_period_rows:
        if candidate.get("isMadeShot") or candidate.get("isMissedShot"):
            return to_int_or_none(candidate.get("teamId"))
        if candidate.get("isTurnover"):
            return to_int_or_none(candidate.get("teamId"))
        if is_non_technical_free_throw_row(candidate):
            return to_int_or_none(candidate.get("teamId"))

    return None


def resolve_offense_team_ids(
    rows: list[dict[str, Any]],
    boxscore_context: dict[str, Any],
) -> None:
    """Populate offense team ids using possession and period-start inference."""
    for index, row in enumerate(rows):
        offense_team_id = to_int_or_none(row.get("possession"))
        if offense_team_id is not None and offense_team_id <= 0:
            offense_team_id = None
        if is_start_of_period_row(row):
            offense_team_id = team_starting_period_with_ball(rows, index)
        elif (
            row.get("isRebound")
            and normalized_action_type(row.get("subType")) == "defensive"
            and index > 0
            and rows[index - 1].get("gameId") == row.get("gameId")
            and rows[index - 1].get("period") == row.get("period")
            and rows[index - 1].get("resolvedOffenseTeamId") is not None
        ):
            # Match pbpstats live semantics: a defensive rebound still belongs
            # to the possession that just ended, and the offense flips on the
            # following event rather than on the rebound row itself.
            offense_team_id = to_int_or_none(rows[index - 1].get("resolvedOffenseTeamId"))
        row["resolvedOffenseTeamId"] = offense_team_id

    for index, row in enumerate(rows):
        if row.get("resolvedOffenseTeamId") is not None:
            continue
        previous_row = rows[index - 1] if index > 0 else None
        if (
            previous_row is not None
            and previous_row.get("gameId") == row.get("gameId")
            and previous_row.get("period") == row.get("period")
            and previous_row.get("resolvedOffenseTeamId") is not None
        ):
            row["resolvedOffenseTeamId"] = previous_row.get("resolvedOffenseTeamId")


def apply_phase2_row_context(
    rows: list[dict[str, Any]],
    boxscore_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Add Phase 2 offense/defense, score, and possession-boundary context."""
    teams = boxscore_context.get("teams") or {}
    team_ids = team_ids_from_boxscore_context(boxscore_context)
    resolve_offense_team_ids(rows, boxscore_context)

    last_possession_end_index_by_period: dict[tuple[str | None, int | None], int] = {}

    for index, row in enumerate(rows):
        previous_row = rows[index - 1] if index > 0 else None
        next_row = rows[index + 1] if index + 1 < len(rows) else None

        same_period_previous = (
            previous_row is not None
            and previous_row.get("gameId") == row.get("gameId")
            and previous_row.get("period") == row.get("period")
        )
        same_period_next = (
            next_row is not None
            and next_row.get("gameId") == row.get("gameId")
            and next_row.get("period") == row.get("period")
        )

        offense_team_id = to_int_or_none(row.get("resolvedOffenseTeamId"))
        defense_team_id = other_team_id(offense_team_id, team_ids)
        row["resolvedDefenseTeamId"] = defense_team_id

        offense_team_meta = teams.get(offense_team_id) if offense_team_id is not None else None
        defense_team_meta = teams.get(defense_team_id) if defense_team_id is not None else None
        row["offenseHomeAway"] = None if offense_team_meta is None else offense_team_meta.get("location")
        row["defenseHomeAway"] = None if defense_team_meta is None else defense_team_meta.get("location")

        if (
            previous_row is None
            or row.get("gameId") != previous_row.get("gameId")
        ):
            before_home, before_away = score_pair_from_row(row)
        elif is_start_of_period_row(row):
            before_home, before_away = score_pair_from_row(row)
        else:
            before_home, before_away = score_pair_from_row(previous_row)
        after_home, after_away = score_pair_from_row(row)
        row["scoreMarginBefore"] = score_margin_from_offense_team(
            offense_team_id,
            before_home,
            before_away,
            teams,
        )
        row["scoreMarginAfter"] = score_margin_from_offense_team(
            offense_team_id,
            after_home,
            after_away,
            teams,
        )

        next_offense_team_id = (
            to_int_or_none(next_row.get("resolvedOffenseTeamId"))
            if same_period_next
            else None
        )

        is_possession_ending_event = False
        if not same_period_next:
            is_possession_ending_event = True
        elif is_start_of_period_row(row) or is_start_of_period_row(next_row):
            is_possession_ending_event = False
        elif (
            offense_team_id is not None
            and next_offense_team_id is not None
            and offense_team_id > 0
            and next_offense_team_id > 0
            and offense_team_id != next_offense_team_id
        ):
            is_possession_ending_event = True

        row["isPossessionEndingEvent"] = is_possession_ending_event

        period_key = (row.get("gameId"), to_int_or_none(row.get("period")))
        count_as_possession = False
        if is_possession_ending_event:
            current_seconds = to_float_or_none(row.get("secondsRemainingInPeriod"))
            if current_seconds is not None and current_seconds > 2:
                count_as_possession = True
            else:
                previous_end_index = last_possession_end_index_by_period.get(period_key)
                previous_end_seconds = (
                    to_float_or_none(rows[previous_end_index].get("secondsRemainingInPeriod"))
                    if previous_end_index is not None
                    else None
                )
                if previous_end_seconds is None or previous_end_seconds > 2:
                    count_as_possession = True
                else:
                    start_index = 0 if previous_end_index is None else previous_end_index + 1
                    count_as_possession = any(
                        rows[event_index].get("isFreeThrow") or rows[event_index].get("isMadeShot")
                        for event_index in range(start_index, index + 1)
                        if rows[event_index].get("gameId") == row.get("gameId")
                        and rows[event_index].get("period") == row.get("period")
                    )
            last_possession_end_index_by_period[period_key] = index
        row["countAsPossession"] = count_as_possession

        if not is_possession_ending_event:
            row["possessionBoundaryReason"] = None
        elif row.get("isMadeShot"):
            row["possessionBoundaryReason"] = "made_shot"
        elif row.get("isTurnover"):
            row["possessionBoundaryReason"] = "turnover"
        elif row.get("isRebound") and next_offense_team_id is not None and offense_team_id != next_offense_team_id:
            row["possessionBoundaryReason"] = "def_rebound"
        elif row.get("isFreeThrow") and next_offense_team_id is not None and offense_team_id != next_offense_team_id:
            row["possessionBoundaryReason"] = "free_throw"
        elif row.get("isJumpBall") and next_offense_team_id is not None and offense_team_id != next_offense_team_id:
            row["possessionBoundaryReason"] = "jump_ball_change"
        elif not same_period_next:
            row["possessionBoundaryReason"] = "period_end"
        else:
            row["possessionBoundaryReason"] = "offense_change"

    return rows


def normalized_qualifiers(value: Any) -> set[str]:
    """Return normalized qualifier strings for one row."""
    qualifiers = value if isinstance(value, list) else []
    normalized_values: set[str] = set()
    for qualifier in qualifiers:
        normalized = normalized_action_type(qualifier)
        if normalized is not None:
            normalized_values.add(normalized)
    return normalized_values


def free_throw_trip_numbers(row: dict[str, Any]) -> tuple[int | None, int | None]:
    """Parse free throw trip position from subtype like '2 of 3'."""
    sub_type = null_if_empty(row.get("subType"))
    if sub_type is None:
        return None, None
    match = re.fullmatch(r"\s*(\d+)\s+of\s+(\d+)\s*", str(sub_type), flags=re.IGNORECASE)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def is_end_free_throw_row(row: dict[str, Any]) -> bool:
    """Return True when the free throw is the final live shot in the trip."""
    if not row.get("isFreeThrow"):
        return False
    trip_number, trip_size = free_throw_trip_numbers(row)
    if trip_number is None or trip_size is None:
        return False
    descriptor = normalized_action_type(row.get("descriptor"))
    if descriptor in {"technical", "flagrant", "awayfromplay", "inbound"}:
        return False
    return trip_number == trip_size


def is_missed_free_throw_row(row: dict[str, Any]) -> bool:
    """Return True when the row is a missed free throw attempt."""
    if not row.get("isFreeThrow"):
        return False
    shot_result = null_if_empty(row.get("shotResult"))
    return shot_result is not None and str(shot_result).strip().lower() == "missed"


def event_team_ids(rows: list[dict[str, Any]], boxscore_context: dict[str, Any]) -> list[int]:
    """Return known team ids from boxscore context with row-based fallback."""
    team_ids = team_ids_from_boxscore_context(boxscore_context)
    if team_ids:
        return team_ids

    discovered_ids: set[int] = set()
    for row in rows:
        for field in ("teamId", "resolvedOffenseTeamId", "resolvedDefenseTeamId", "possession"):
            team_id = to_int_or_none(row.get(field))
            if team_id is not None and team_id > 0:
                discovered_ids.add(team_id)
    return sorted(discovered_ids)


def apply_phase6_row_context(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add remaining period-opening and event-linkage semantics."""
    action_lookup = {
        (row.get("gameId"), to_int_or_none(row.get("actionNumber"))): row
        for row in rows
        if to_int_or_none(row.get("actionNumber")) is not None
    }

    for index, row in enumerate(rows):
        row["isPeriodStartEvent"] = is_start_of_period_row(row)
        row["isPeriodEndEvent"] = is_end_of_period_row(row)
        row["teamStartingPeriodWithBall"] = (
            team_starting_period_with_ball(rows, index)
            if row["isPeriodStartEvent"]
            else None
        )

        linked_shot_action_number = None
        rebound_of_missed_shot_flag = False
        if row.get("isRebound"):
            linked_shot = find_row_by_action_number(action_lookup, row, row.get("shotActionNumber"))
            if linked_shot is not None:
                linked_shot_action_number = to_int_or_none(linked_shot.get("actionNumber"))
                rebound_of_missed_shot_flag = bool(
                    linked_shot.get("isMissedShot") or is_missed_free_throw_row(linked_shot)
                )
        row["linkedShotActionNumber"] = linked_shot_action_number
        row["reboundOfMissedShotFlag"] = rebound_of_missed_shot_flag

        trip_number, trip_size = free_throw_trip_numbers(row)
        row["freeThrowTripSequenceNum"] = trip_number
        row["freeThrowTripSize"] = trip_size

    return rows


def next_non_replay_same_period_row(
    rows: list[dict[str, Any]],
    index: int,
) -> dict[str, Any] | None:
    """Return the next non-replay row in the same game period."""
    row = rows[index]
    for candidate in rows[index + 1 :]:
        if candidate.get("gameId") != row.get("gameId") or candidate.get("period") != row.get("period"):
            return None
        if normalized_action_type(candidate.get("actionType")) != "instantreplay":
            return candidate
    return None


def foul_counts_towards_penalty(row: dict[str, Any]) -> bool:
    """Match pbpstats live foul types that reduce fouls to give."""
    if not row.get("isFoul"):
        return False
    descriptor = normalized_action_type(row.get("descriptor"))
    sub_type = normalized_action_type(row.get("subType"))
    if sub_type == "personal" and descriptor is None:
        return True
    if descriptor == "shooting":
        return True
    if descriptor == "looseball":
        return True
    if descriptor == "inbound":
        return True
    if descriptor == "awayfromplay":
        return True
    if descriptor == "clearpath":
        return True
    if descriptor in {"flagranttype1", "flagranttype2"}:
        return True
    if descriptor in {"block", "take", "transition"}:
        return True
    return False


def find_row_by_action_number(
    action_lookup: dict[tuple[str | None, int | None], dict[str, Any]],
    row: dict[str, Any],
    action_number: Any,
) -> dict[str, Any] | None:
    """Look up another action row in the same game by action number."""
    action_num = to_int_or_none(action_number)
    if action_num is None:
        return None
    return action_lookup.get((row.get("gameId"), action_num))


def rebound_is_placeholder(
    rows: list[dict[str, Any]],
    index: int,
    action_lookup: dict[tuple[str | None, int | None], dict[str, Any]],
) -> bool:
    """Match pbpstats live rebound is_placeholder behavior."""
    row = rows[index]
    if not row.get("isRebound"):
        return False

    qualifiers = normalized_qualifiers(row.get("qualifiers"))
    if "deadball" in qualifiers:
        return True

    linked_shot = find_row_by_action_number(action_lookup, row, row.get("shotActionNumber"))
    if linked_shot is not None and linked_shot.get("isFlagrantFt"):
        return True

    return False


def rebound_is_real(
    rows: list[dict[str, Any]],
    index: int,
    action_lookup: dict[tuple[str | None, int | None], dict[str, Any]],
) -> bool:
    """Match pbpstats live rebound is_real_rebound behavior closely enough for sequencing."""
    row = rows[index]
    if not row.get("isRebound"):
        return False
    if rebound_is_placeholder(rows, index, action_lookup):
        return False

    linked_shot = find_row_by_action_number(action_lookup, row, row.get("shotActionNumber"))
    if linked_shot is not None and linked_shot.get("isFreeThrow") and not is_end_free_throw_row(linked_shot):
        return False

    person_id = to_int_or_none(row.get("personId")) or 0
    if person_id == 0:
        current_seconds = to_float_or_none(row.get("secondsRemainingInPeriod"))
        for candidate in rows:
            if candidate is row:
                continue
            if candidate.get("gameId") != row.get("gameId") or candidate.get("period") != row.get("period"):
                continue
            if to_float_or_none(candidate.get("secondsRemainingInPeriod")) != current_seconds:
                continue
            candidate_action_type = normalized_action_type(candidate.get("actionType"))
            candidate_sub_type = normalized_action_type(candidate.get("subType"))
            if candidate_action_type == "turnover" and candidate_sub_type == "shotclock":
                return False
            if candidate_action_type == "violation" and candidate_sub_type == "kickedball":
                return False

    seconds_remaining = to_float_or_none(row.get("secondsRemainingInPeriod"))
    next_row = next_non_replay_same_period_row(rows, index)

    if person_id == 0 and seconds_remaining == 0 and (next_row is None or is_end_of_period_row(next_row)):
        return False

    if (
        linked_shot is not None
        and person_id == 0
        and seconds_remaining is not None
        and seconds_remaining <= 3
        and seconds_remaining == to_float_or_none(linked_shot.get("secondsRemainingInPeriod"))
        and next_row is not None
        and is_end_of_period_row(next_row)
    ):
        return False

    return True


def inferred_rebound_type_from_linked_shot(
    row: dict[str, Any],
    action_lookup: dict[tuple[str | None, int | None], dict[str, Any]],
) -> str | None:
    """Infer rebound side from linked missed-shot team vs rebound team."""
    if not row.get("isRebound"):
        return None

    linked_shot = find_row_by_action_number(action_lookup, row, row.get("shotActionNumber"))
    if linked_shot is None:
        return None

    rebound_team_id = to_int_or_none(row.get("teamId"))
    shot_team_id = to_int_or_none(linked_shot.get("teamId"))
    if rebound_team_id is None or shot_team_id is None:
        return None

    return "offensive" if rebound_team_id == shot_team_id else "defensive"


def previous_same_period_index(rows: list[dict[str, Any]], index: int) -> int | None:
    """Return previous row index in same game and period."""
    row = rows[index]
    previous_index = index - 1
    if previous_index < 0:
        return None
    previous_row = rows[previous_index]
    if previous_row.get("gameId") != row.get("gameId") or previous_row.get("period") != row.get("period"):
        return None
    return previous_index


def find_foul_that_led_to_free_throw(
    rows: list[dict[str, Any]],
    index: int,
) -> int | None:
    """Walk backward to the foul that started the current free-throw sequence."""
    row = rows[index]
    search_index = previous_same_period_index(rows, index)
    while search_index is not None:
        candidate = rows[search_index]
        if candidate.get("isFoul"):
            return search_index
        if candidate.get("isPossessionEndingEvent") and not candidate.get("isFreeThrow"):
            return None
        search_index = previous_same_period_index(rows, search_index)
    return None


def find_foul_index_for_penalty_context(
    rows: list[dict[str, Any]],
    index: int,
    action_lookup: dict[tuple[str | None, int | None], dict[str, Any]],
) -> int | None:
    """Return foul index for current foul / free throw / missed-FT rebound penalty checks."""
    row = rows[index]
    if row.get("isFoul"):
        return index
    if row.get("isFreeThrow"):
        return find_foul_that_led_to_free_throw(rows, index)
    if row.get("isRebound") and row.get("isDreb"):
        linked_shot = find_row_by_action_number(action_lookup, row, row.get("shotActionNumber"))
        if linked_shot is not None and linked_shot.get("isFreeThrow"):
            linked_index = previous_same_period_index(rows, index)
            while linked_index is not None:
                candidate = rows[linked_index]
                if candidate.get("actionNumber") == linked_shot.get("actionNumber"):
                    return find_foul_that_led_to_free_throw(rows, linked_index)
                linked_index = previous_same_period_index(rows, linked_index)
    return None


def apply_phase3_row_context(
    rows: list[dict[str, Any]],
    boxscore_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Add Phase 3 foul-state and advanced semantic flags."""
    team_ids = event_team_ids(rows, boxscore_context)
    action_lookup = {
        (row.get("gameId"), to_int_or_none(row.get("actionNumber"))): row
        for row in rows
        if to_int_or_none(row.get("actionNumber")) is not None
    }

    current_period_key: tuple[str | None, int | None] | None = None
    fouls_to_give_by_team: dict[int, int] = {}

    for index, row in enumerate(rows):
        period_key = (row.get("gameId"), to_int_or_none(row.get("period")))
        if index == 0 or is_start_of_period_row(row):
            current_period_key = period_key
            default_fouls_to_give = 4 if (period_key[1] or 0) <= 4 else 3
            fouls_to_give_by_team = {
                team_id: default_fouls_to_give
                for team_id in team_ids
            }

        seconds_remaining = to_float_or_none(row.get("secondsRemainingInPeriod"))
        if seconds_remaining is not None and seconds_remaining <= 120:
            fouls_to_give_by_team = {
                team_id: min(value, 1)
                for team_id, value in fouls_to_give_by_team.items()
            }

        row["_foulsToGiveBeforeByTeam"] = fouls_to_give_by_team.copy()

        fouling_team_id = to_int_or_none(row.get("teamId"))
        if (
            foul_counts_towards_penalty(row)
            and fouling_team_id is not None
            and fouling_team_id in fouls_to_give_by_team
            and fouls_to_give_by_team[fouling_team_id] > 0
        ):
            fouls_to_give_by_team[fouling_team_id] -= 1

        row["_foulsToGiveAfterByTeam"] = fouls_to_give_by_team.copy()

        offense_team_id = to_int_or_none(row.get("resolvedOffenseTeamId"))
        defense_team_id = to_int_or_none(row.get("resolvedDefenseTeamId"))
        row["foulsToGiveOffense"] = (
            fouls_to_give_by_team.get(offense_team_id)
            if offense_team_id is not None
            else None
        )
        row["foulsToGiveDefense"] = (
            fouls_to_give_by_team.get(defense_team_id)
            if defense_team_id is not None
            else None
        )

        qualifiers = normalized_qualifiers(row.get("qualifiers"))
        sub_type = normalized_action_type(row.get("subType"))
        descriptor = normalized_action_type(row.get("descriptor"))

        row["isOreb"] = bool(row.get("isRebound") and sub_type == "offensive")
        row["isDreb"] = bool(row.get("isRebound") and sub_type == "defensive")
        inferred_rebound_type = inferred_rebound_type_from_linked_shot(row, action_lookup)
        row["inferredReboundType"] = inferred_rebound_type
        row["reboundTypeSourceMismatchFlag"] = bool(
            row.get("isRebound")
            and inferred_rebound_type is not None
            and sub_type in {"offensive", "defensive"}
            and inferred_rebound_type != sub_type
        )
        row["isPlaceholderRebound"] = rebound_is_placeholder(rows, index, action_lookup)
        row["isShootingFoul"] = bool(row.get("isFoul") and descriptor == "shooting")
        row["isTechnicalFt"] = bool(row.get("isFreeThrow") and descriptor == "technical")
        row["isFlagrantFt"] = bool(row.get("isFreeThrow") and descriptor == "flagrant")

        is_turnover = bool(row.get("isTurnover"))
        has_steal = to_int_or_none(row.get("stealPersonId")) is not None
        row["isBadPassTurnover"] = bool(is_turnover and has_steal and sub_type == "badpass")
        row["isLostBallTurnover"] = bool(is_turnover and has_steal and sub_type == "lostball")
        row["isTravelTurnover"] = bool(is_turnover and sub_type == "traveling")
        row["isShotClockTurnover"] = bool(is_turnover and sub_type == "shotclock")

    for index, row in enumerate(rows):
        row["isSecondChanceEvent"] = False
        search_index = previous_same_period_index(rows, index)
        if search_index is not None:
            previous_row = rows[search_index]
            if (
                previous_row.get("isRebound")
                and previous_row.get("isOreb")
                and rebound_is_real(rows, search_index, action_lookup)
            ):
                row["isSecondChanceEvent"] = True
            else:
                while search_index is not None:
                    previous_row = rows[search_index]
                    if previous_row.get("isPossessionEndingEvent"):
                        break
                    if (
                        previous_row.get("isRebound")
                        and previous_row.get("isOreb")
                        and rebound_is_real(rows, search_index, action_lookup)
                    ):
                        row["isSecondChanceEvent"] = True
                        break
                    search_index = previous_same_period_index(rows, search_index)

        offense_team_id = to_int_or_none(row.get("resolvedOffenseTeamId"))
        defense_team_id = to_int_or_none(row.get("resolvedDefenseTeamId"))
        fouls_after = row.get("_foulsToGiveAfterByTeam") or {}
        row["isPenaltyEvent"] = False
        if defense_team_id is None or fouls_after.get(defense_team_id) != 0:
            continue

        foul_index = find_foul_index_for_penalty_context(rows, index, action_lookup)
        if foul_index is None:
            row["isPenaltyEvent"] = True
            continue

        foul_row = rows[foul_index]
        foul_before = foul_row.get("_foulsToGiveBeforeByTeam") or {}
        if foul_before.get(defense_team_id, 0) == 0:
            row["isPenaltyEvent"] = True

    return rows


def apply_phase1_row_context(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add Phase 1 neighboring-event context after base rows are built."""
    for index, row in enumerate(rows):
        previous_row = rows[index - 1] if index > 0 else None
        next_row = rows[index + 1] if index + 1 < len(rows) else None

        same_period_previous = (
            previous_row is not None
            and previous_row.get("gameId") == row.get("gameId")
            and previous_row.get("period") == row.get("period")
        )
        same_period_next = (
            next_row is not None
            and next_row.get("gameId") == row.get("gameId")
            and next_row.get("period") == row.get("period")
        )

        row["prevActionNumber"] = (
            None
            if is_start_of_period_row(row)
            else previous_row.get("actionNumber") if same_period_previous else None
        )
        row["nextActionNumber"] = next_row.get("actionNumber") if same_period_next else None
        row["prevOrderNumber"] = (
            None
            if is_start_of_period_row(row)
            else previous_row.get("orderNumber") if same_period_previous else None
        )
        row["nextOrderNumber"] = next_row.get("orderNumber") if same_period_next else None

        current_seconds = to_float_or_none(row.get("secondsRemainingInPeriod"))
        previous_seconds = (
            to_float_or_none(previous_row.get("secondsRemainingInPeriod"))
            if same_period_previous
            else None
        )
        if current_seconds is None:
            row["secondsSincePreviousEvent"] = None
        elif previous_seconds is None:
            row["secondsSincePreviousEvent"] = 0.0
        else:
            row["secondsSincePreviousEvent"] = max(previous_seconds - current_seconds, 0.0)

    return rows


def extract_game_id_from_key(key: str) -> str | None:
    """Extract game_id value from key formatted like game_id=XXXX.json."""
    filename = key.rsplit("/", 1)[-1]
    if not filename.startswith("game_id=") or not filename.endswith(".json"):
        return None
    raw_game_id = filename[len("game_id=") : -len(".json")] or None
    return normalize_game_id(raw_game_id)


def parse_s3_path(s3_path: str) -> tuple[str, str]:
    """Parse and validate an s3://bucket/key path."""
    parsed = urlparse(s3_path)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        raise ValueError(
            f"Invalid TARGET_SOURCE_S3_PATH: {s3_path}. Expected s3://bucket/key"
        )
    return parsed.netloc, parsed.path.lstrip("/")


def list_json_objects(s3_client) -> list[dict[str, Any]]:
    """List all .json objects under source prefix using pagination."""
    paginator = s3_client.get_paginator("list_objects_v2")
    objects: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=SOURCE_PREFIX):
        for obj in page.get("Contents", []):
            key = obj.get("Key", "")
            if key.endswith(".json"):
                objects.append(obj)
    return objects


def parse_state_datetime(value: Any) -> datetime | None:
    """Parse persisted state datetime string into UTC datetime."""
    return shared_parse_state_datetime(value)


def state_datetime_to_iso(value: datetime | None) -> str | None:
    """Serialize datetime to ISO Z string."""
    return shared_state_datetime_to_iso(value)


def read_state(s3_client) -> dict[str, Any]:
    """Load incremental state from S3, returning empty state when absent."""
    return read_json_state(s3_client=s3_client, bucket=S3_BUCKET, key=STATE_KEY)


def write_state(s3_client, state: dict[str, Any]) -> None:
    """Persist incremental state to S3 as JSON."""
    write_json_state(s3_client=s3_client, bucket=S3_BUCKET, key=STATE_KEY, state=state)


def select_incremental_game_ids_from_legacy_state(
    source_index: dict[str, list[dict[str, Any]]],
    state: dict[str, Any],
) -> tuple[set[str], dict[str, Any]]:
    """Return game_ids selected by the legacy watermark + lookback policy."""
    return select_incremental_game_ids_from_watermark_state(
        source_index,
        state,
        lookback_minutes=INCREMENTAL_LOOKBACK_MINUTES,
    )


def read_json_payload(s3_client, key: str) -> dict[str, Any]:
    """Read and decode one JSON payload from S3."""
    response = s3_client.get_object(Bucket=S3_BUCKET, Key=key)
    payload_bytes = response["Body"].read()
    return json.loads(payload_bytes)


def boxscore_key_for_game(game_id: str) -> str:
    """Return raw boxscore key for one game."""
    return f"{BOXSCORE_PREFIX}game_id={game_id}.json"


def build_boxscore_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a lightweight enrichment context from raw boxscore payload."""
    game = payload.get("game") or {}
    game_datetime_est = null_if_empty(game.get("gameEt")) or null_if_empty(game.get("gameTimeUTC"))

    teams: dict[int, dict[str, Any]] = {}
    player_full_name_by_id: dict[int, str] = {}
    player_name_by_id: dict[int, str] = {}
    name_to_person_ids: dict[str, set[int]] = {}

    for team_key in ("homeTeam", "awayTeam"):
        team = game.get(team_key) or {}
        team_id = to_int_or_none(team.get("teamId"))
        if team_id is None:
            continue

        teams[team_id] = {
            "teamCity": null_if_empty(team.get("teamCity")),
            "teamName": null_if_empty(team.get("teamName")),
            "teamTricode": null_if_empty(team.get("teamTricode")),
            "location": "h" if team_key == "homeTeam" else "v",
        }

        for player in team.get("players") or []:
            if not isinstance(player, dict):
                continue
            person_id = to_int_or_none(player.get("personId"))
            if person_id is None:
                continue
            full_name = (
                null_if_empty(player.get("name"))
                or " ".join(
                    part
                    for part in [
                        null_if_empty(player.get("firstName")),
                        null_if_empty(player.get("familyName")),
                    ]
                    if part
                )
                or null_if_empty(player.get("nameI"))
            )
            if full_name:
                player_full_name_by_id[person_id] = full_name
            player_name = (
                null_if_empty(player.get("familyName"))
                or null_if_empty(player.get("playerName"))
                or null_if_empty(player.get("lastName"))
            )
            if player_name:
                player_name_by_id[person_id] = str(player_name)

            candidate_names = [
                full_name,
                null_if_empty(player.get("name")),
                null_if_empty(player.get("nameI")),
                null_if_empty(player.get("familyName")),
                " ".join(
                    part
                    for part in [
                        null_if_empty(player.get("firstName")),
                        null_if_empty(player.get("familyName")),
                    ]
                    if part
                )
                or None,
            ]
            for candidate_name in candidate_names:
                normalized = normalize_name(candidate_name)
                if normalized is None:
                    continue
                name_to_person_ids.setdefault(normalized, set()).add(person_id)

    opponent_by_team_id: dict[int, dict[str, Any]] = {}
    if len(teams) == 2:
        team_ids = list(teams.keys())
        opponent_by_team_id[team_ids[0]] = teams[team_ids[1]]
        opponent_by_team_id[team_ids[1]] = teams[team_ids[0]]

    return {
        "gameDateTimeEst": game_datetime_est,
        "teams": teams,
        "opponents": opponent_by_team_id,
        "player_full_name_by_id": player_full_name_by_id,
        "player_name_by_id": player_name_by_id,
        "name_to_person_ids": name_to_person_ids,
    }


def load_boxscore_context_for_game(s3_client, game_id: str | None) -> dict[str, Any]:
    """Load boxscore context for one game; return empty context if unavailable."""
    if game_id is None:
        return {}
    key = boxscore_key_for_game(game_id)
    try:
        payload = read_json_payload(s3_client, key)
    except (json.JSONDecodeError, UnicodeDecodeError, BotoCoreError, ClientError, OSError):
        try:
            response = requests.get(
                CDN_BOXSCORE_URL_TEMPLATE.format(game_id=str(game_id).zfill(10)),
                headers=CDN_REQUEST_HEADERS,
                timeout=CDN_REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
        except (
            requests.RequestException,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ):
            return {}
    return build_boxscore_context(payload)


def derive_shot_value(action: dict[str, Any]) -> int | None:
    """Derive simple shot value from the action type."""
    action_type = null_if_empty(action.get("actionType"))
    if action_type is None:
        return None

    normalized = str(action_type).strip().lower()
    if normalized == "3pt":
        return 3
    if normalized == "2pt":
        return 2
    if normalized == "freethrow":
        return 1
    return None


def parse_replaced_by_sub(
    description: Any,
    name_to_person_ids: dict[str, set[int]],
) -> int | None:
    """Extract incoming player id from legacy 'replaced by' substitution text."""
    description = null_if_empty(description)
    if description is None:
        return None
    text = str(description).strip()
    match = re.search(r"replaced by\s+(.*)$", text, flags=re.IGNORECASE)
    if not match:
        return None
    incoming_name = normalize_name(match.group(1))
    if incoming_name is None:
        return None
    candidates = sorted(name_to_person_ids.get(incoming_name, set()))
    if len(candidates) == 1:
        return candidates[0]
    return None


def enrich_action_row(action: dict[str, Any], boxscore_context: dict[str, Any]) -> dict[str, Any]:
    """Derive easy enrichment fields from raw boxscore context plus action values."""
    player_full_name_by_id = boxscore_context.get("player_full_name_by_id") or {}
    player_name_by_id = boxscore_context.get("player_name_by_id") or {}
    name_to_person_ids = boxscore_context.get("name_to_person_ids") or {}
    teams = boxscore_context.get("teams") or {}
    opponents = boxscore_context.get("opponents") or {}

    team_id = to_int_or_none(action.get("teamId"))
    team_meta = teams.get(team_id) if team_id is not None else None
    opponent_meta = opponents.get(team_id) if team_id is not None else None

    def full_name_from_person(
        person_field: str,
        fallback_field: str | None = None,
        raw_person_value: Any | None = None,
    ) -> str | None:
        person_id = to_int_or_none(action.get(person_field) if raw_person_value is None else raw_person_value)
        if person_id is not None:
            full_name = player_full_name_by_id.get(person_id)
            if full_name:
                return full_name
        if fallback_field is not None:
            fallback_value = null_if_empty(action.get(fallback_field))
            if fallback_value is not None:
                return str(fallback_value)
        return None

    jump_ball_recovered_person_id_raw = action.get("jumpBallRecoveredPersonId")
    if null_if_empty(jump_ball_recovered_person_id_raw) is None:
        jump_ball_recovered_person_id_raw = action.get("jumpBallRecoverdPersonId")

    subs_in_person_id = parse_replaced_by_sub(action.get("description"), name_to_person_ids)

    return {
        "gameDateTimeEst": boxscore_context.get("gameDateTimeEst"),
        "assistFullName": full_name_from_person("assistPersonId", "assistPlayerName"),
        "blockFullName": full_name_from_person("blockPersonId", "blockPlayerName"),
        "foulDrawnFullName": full_name_from_person("foulDrawnPersonId", "foulDrawnPlayerName"),
        "jumpBallLostFullName": full_name_from_person("jumpBallLostPersonId", "jumpBallLostPlayerName"),
        "jumpBallRecoveredFullName": full_name_from_person(
            "jumpBallRecoveredPersonId",
            "jumpBallRecoveredName",
            jump_ball_recovered_person_id_raw,
        ),
        "jumpBallWonFullName": full_name_from_person("jumpBallWonPersonId", "jumpBallWonPlayerName"),
        "location": None if team_meta is None else team_meta.get("location"),
        "playerFullName": full_name_from_person("personId", "playerName"),
        "playerteamCity": None if team_meta is None else team_meta.get("teamCity"),
        "playerteamName": None if team_meta is None else team_meta.get("teamName"),
        "opponentteamCity": None if opponent_meta is None else opponent_meta.get("teamCity"),
        "opponentteamName": None if opponent_meta is None else opponent_meta.get("teamName"),
        "shotValue": derive_shot_value(action),
        "stealFullName": full_name_from_person("stealPersonId", "stealPlayerName"),
        "subsInFullName": None if subs_in_person_id is None else player_full_name_by_id.get(subs_in_person_id),
        "subsInPersonId": subs_in_person_id,
        "subsInPlayerName": None if subs_in_person_id is None else player_name_by_id.get(subs_in_person_id),
    }


def normalize_action_value(column: str, raw_value: Any) -> Any:
    """Normalize one action field according to schema conversion rules."""
    if column in {"edited", "timeActual"}:
        raw_value = null_if_empty(raw_value)
        return None if raw_value is None else str(raw_value)
    if column == "value":
        raw_value = null_if_empty(raw_value)
        return None if raw_value is None else str(raw_value)

    if column == "personIdsFilter":
        return to_int_list_or_none(raw_value)
    if column == "qualifiers":
        return to_str_list_or_none(raw_value)
    if column in INT_FIELDS:
        return to_int_or_none(raw_value)
    if column in FLOAT_FIELDS:
        return to_float_or_none(raw_value)
    if column in BOOL_FIELDS:
        return to_bool_or_none(raw_value)

    raw_value = null_if_empty(raw_value)
    return None if raw_value is None else str(raw_value)


def build_rows_from_payload(
    payload: dict[str, Any],
    fallback_game_id: str | None,
    boxscore_context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Build action rows from one game payload."""
    game = payload.get("game") or {}
    game_id = normalize_game_id(game.get("gameId")) or normalize_game_id(fallback_game_id)
    actions = game.get("actions") or []
    if not isinstance(actions, list):
        actions = []
    boxscore_context = boxscore_context or {}

    rows: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue

        # Source has an occasional typo key: jumpBallRecoverdPersonId.
        # Canonicalize both variants into jumpBallRecoveredPersonId in silver.
        jump_ball_recovered_person_id_raw = action.get("jumpBallRecoveredPersonId")
        if null_if_empty(jump_ball_recovered_person_id_raw) is None:
            jump_ball_recovered_person_id_raw = action.get("jumpBallRecoverdPersonId")

        row: dict[str, Any] = {"gameId": game_id}
        enrichments = enrich_action_row(action, boxscore_context)
        enrichments.update(derive_phase1_event_enrichments(action))
        for column in ACTION_COLUMNS:
            if column in enrichments:
                row[column] = normalize_action_value(column, enrichments[column])
            elif column == "jumpBallRecoveredPersonId":
                row[column] = normalize_action_value(column, jump_ball_recovered_person_id_raw)
            else:
                row[column] = normalize_action_value(column, action.get(column))
        rows.append(row)

    rows = apply_phase1_row_context(rows)
    rows = apply_phase2_row_context(rows, boxscore_context)
    rows = apply_phase3_row_context(rows, boxscore_context)
    rows = apply_phase6_row_context(rows)
    return rows, game_id


def destination_key_for_game(game_id: str) -> str:
    """Build destination parquet key for one game."""
    normalized_game_id = normalize_game_id(game_id)
    if normalized_game_id is None:
        raise ValueError("game_id is required to build playbyplay destination key")
    return f"{DESTINATION_PREFIX}game_id={normalized_game_id}.parquet"


def add_silver_metadata(
    rows: list[dict[str, Any]],
    *,
    pipeline_run_id: str,
    ingested_at_utc: datetime,
    source_key: str,
    source_last_modified_utc: datetime | None,
) -> list[dict[str, Any]]:
    """Append standardized silver metadata fields to event rows."""
    normalized_last_modified = source_last_modified_utc
    if isinstance(normalized_last_modified, datetime) and normalized_last_modified.tzinfo is None:
        normalized_last_modified = normalized_last_modified.replace(tzinfo=timezone.utc)

    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        enriched_row = dict(row)
        enriched_row["_meta_pipeline_run_id"] = pipeline_run_id
        enriched_row["_meta_ingested_at_utc"] = ingested_at_utc
        enriched_row["_meta_source_system"] = META_SOURCE_SYSTEM
        enriched_row["_meta_source_key"] = source_key
        enriched_row["_meta_source_last_modified_utc"] = normalized_last_modified
        enriched_row["_meta_schema_version"] = META_SCHEMA_VERSION
        enriched_rows.append(enriched_row)
    return enriched_rows


def write_game_parquet_to_s3(game_id: str, rows: list[dict[str, Any]], s3_client) -> None:
    """Write one game parquet object to destination key."""
    normalized_game_id = normalize_game_id(game_id)
    if normalized_game_id is None:
        raise ValueError("game_id is required to write playbyplay parquet")
    table = pa.Table.from_pylist(rows, schema=TARGET_SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    destination_key = destination_key_for_game(normalized_game_id)

    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key=destination_key,
        Body=buffer.getvalue(),
        ContentType="application/octet-stream",
    )


def main() -> None:
    """Run full raw play-by-play to per-game silver parquet transform."""
    s3_client = boto3.client("s3")
    ingested_at_utc = datetime.now(timezone.utc)
    pipeline_run_id = f"playbyplay_events_{ingested_at_utc.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    keys: list[str] = []
    source_last_modified_by_key: dict[str, datetime | None] = {}
    source_index: dict[str, list[dict[str, Any]]] = {}
    selection_meta: dict[str, Any] = {
        "selection_mode": "single_file" if not PROCESS_ALL_FILES else "full_refresh",
        "checkpoint_enabled": False,
        "legacy_state_fallback_used": False,
        "target_game_ids": sorted(TARGET_GAME_IDS),
    }
    state_before: dict[str, Any] = {}
    checkpoint_exists, checkpoint_rows = read_checkpoint_index(
        s3_client=s3_client,
        bucket=S3_BUCKET,
        table_name=TABLE_NAME,
    )
    checkpoint_key_written: str | None = None

    if PROCESS_ALL_FILES:
        objects = list_json_objects(s3_client)
        for obj in objects:
            key = obj.get("Key", "")
            source_last_modified_by_key[key] = normalize_utc_datetime(obj.get("LastModified"))
        source_index = build_source_index_from_objects(
            objects,
            game_id_from_key=extract_game_id_from_key,
        )

        legacy_state = read_state(s3_client) if INCREMENTAL_MODE and not FORCE_FULL_REFRESH else {}
        state_before = legacy_state
        selected_game_ids, selection_meta = select_game_ids_for_processing(
            source_index=source_index,
            target_game_ids=TARGET_GAME_IDS,
            force_full_refresh=(FORCE_FULL_REFRESH or not INCREMENTAL_MODE),
            checkpoint_exists=checkpoint_exists,
            checkpoint_rows=checkpoint_rows,
            legacy_state=legacy_state,
            legacy_fallback_selector=(
                select_incremental_game_ids_from_legacy_state
                if INCREMENTAL_MODE and not FORCE_FULL_REFRESH
                else None
            ),
        )
        keys = [
            source_index[game_id][0]["key"]
            for game_id in selected_game_ids
            if source_index.get(game_id)
        ]
        selection_meta["selected_game_count"] = len(selected_game_ids)
        selection_meta["files_discovered"] = len(objects)
        selection_meta["files_selected"] = len(keys)

        print(f"Mode: {selection_meta.get('selection_mode')}")
        if TARGET_GAME_IDS:
            print(f"Target game ids: {len(TARGET_GAME_IDS)}")

        print(f"Files discovered: {len(objects)}")
        print(f"Files selected: {len(keys)}")
    else:
        if null_if_empty(TARGET_SOURCE_S3_PATH) is None:
            raise ValueError(
                "TARGET_SOURCE_S3_PATH must be set when PROCESS_ALL_FILES is False."
            )

        bucket, key = parse_s3_path(str(TARGET_SOURCE_S3_PATH).strip())
        if bucket != S3_BUCKET:
            raise ValueError(
                f"TARGET_SOURCE_S3_PATH bucket '{bucket}' must match S3_BUCKET '{S3_BUCKET}'."
            )
        if not key.endswith(".json"):
            raise ValueError(
                f"TARGET_SOURCE_S3_PATH must point to a .json file, got key={key}"
            )

        try:
            head_response = s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        except ClientError as exc:
            raise ValueError(
                f"TARGET_SOURCE_S3_PATH does not exist or is inaccessible: s3://{S3_BUCKET}/{key}"
            ) from exc

        keys = [key]
        source_last_modified = normalize_utc_datetime(head_response.get("LastModified"))
        source_last_modified_by_key[key] = source_last_modified
        fallback_game_id = extract_game_id_from_key(key)
        if fallback_game_id is not None:
            source_index[fallback_game_id] = [
                {
                    "key": key,
                    "last_modified_utc": datetime_to_iso(source_last_modified),
                }
            ]
        selection_meta.update(
            {
                "selected_game_count": len(source_index),
                "files_discovered": 1,
                "files_selected": 1,
            }
        )
        print(f"Mode: single file ({TARGET_SOURCE_S3_PATH})")
        print("Files selected: 1")

    games_upserted: set[str] = set()
    total_rows_written = 0
    total_actions_processed = 0
    total_files_processed = 0
    skipped: list[tuple[str | None, str]] = []
    files_with_empty_actions = 0
    max_source_last_modified_seen: datetime | None = None

    for index, key in enumerate(keys, start=1):
        source_last_modified = source_last_modified_by_key.get(key)
        if isinstance(source_last_modified, datetime) and source_last_modified.tzinfo is None:
            source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)
        if isinstance(source_last_modified, datetime):
            if max_source_last_modified_seen is None or source_last_modified > max_source_last_modified_seen:
                max_source_last_modified_seen = source_last_modified

        fallback_game_id = extract_game_id_from_key(key)
        print(
            f"[{index}/{len(keys)}] Processing game_id={fallback_game_id or 'unknown'} "
            f"key={key}"
        )
        try:
            payload = read_json_payload(s3_client, key)
            boxscore_context = load_boxscore_context_for_game(s3_client, fallback_game_id)
            rows, game_id = build_rows_from_payload(payload, fallback_game_id, boxscore_context)
        except (json.JSONDecodeError, UnicodeDecodeError, BotoCoreError, ClientError, OSError) as exc:
            skipped.append((fallback_game_id, key))
            print(
                f"Skipping file game_id={fallback_game_id or 'unknown'} "
                f"key={key} ({type(exc).__name__}: {exc})"
            )
            continue

        total_files_processed += 1
        total_actions_processed += len(rows)

        # Log missing gameId even when file parses, to aid debugging.
        if game_id is None:
            print(f"Warning: missing gameId in payload for key={key}")
            print(f"[{index}/{len(keys)}] Completed with skip (missing gameId)")
            continue

        if len(rows) == 0:
            files_with_empty_actions += 1
            print(
                f"Info: no action rows for game_id={game_id} key={key}; "
                "existing silver parquet left unchanged."
            )
            print(f"[{index}/{len(keys)}] Completed with skip (empty actions) game_id={game_id}")
            continue

        rows = add_silver_metadata(
            rows,
            pipeline_run_id=pipeline_run_id,
            ingested_at_utc=ingested_at_utc,
            source_key=key,
            source_last_modified_utc=source_last_modified,
        )
        write_game_parquet_to_s3(game_id, rows, s3_client)
        games_upserted.add(game_id)
        total_rows_written += len(rows)
        print(
            f"[{index}/{len(keys)}] Completed game_id={game_id} "
            f"rows_written={len(rows)}"
        )

    print(f"Total files scanned: {len(keys)}")
    print(f"Total files processed: {total_files_processed}")
    print(f"Total actions processed: {total_actions_processed}")
    print(f"Total rows written: {total_rows_written}")
    print(f"Games upserted: {len(games_upserted)}")
    print(f"Files with empty actions (not overwritten): {files_with_empty_actions}")
    print(f"Skipped files: {len(skipped)}")

    if skipped:
        print("Skipped game_ids:")
        for skipped_game_id, skipped_key in skipped:
            print(f"- game_id={skipped_game_id or 'unknown'} key={skipped_key}")

    print(f"Wrote parquet files under s3://{S3_BUCKET}/{DESTINATION_PREFIX}")

    warning_reason_counts: dict[str, int] = {}
    warning_count = 0
    if len(skipped) > 0:
        warning_reason_counts["skipped_unreadable_or_invalid_files"] = len(skipped)
        warning_count += len(skipped)
    if files_with_empty_actions > 0:
        warning_reason_counts["files_with_empty_actions"] = files_with_empty_actions
        warning_count += files_with_empty_actions

    if source_index and games_upserted:
        checkpoint_rows_to_write = checkpoint_rows_with_updates(
            existing_rows=checkpoint_rows,
            source_index=source_index,
            written_game_ids=games_upserted,
            processed_at_utc=ingested_at_utc,
            pipeline_run_id=pipeline_run_id,
        )
        checkpoint_key_written = write_checkpoint_index(
            s3_client=s3_client,
            bucket=S3_BUCKET,
            table_name=TABLE_NAME,
            checkpoint_rows=checkpoint_rows_to_write,
        )
        print(f"Wrote checkpoint parquet: s3://{S3_BUCKET}/{checkpoint_key_written}")

    run_status = "success_with_warnings" if warning_count > 0 else "success"
    details_key = write_details_json(
        s3_client=s3_client,
        pipeline_run_id=pipeline_run_id,
        ingested_at_utc=ingested_at_utc,
        details={
            "pipeline_run_id": pipeline_run_id,
            "selection_mode": selection_meta.get("selection_mode"),
            "target_game_ids": selection_meta.get("target_game_ids", []),
            "selected_game_count": selection_meta.get("selected_game_count", 0),
            "written_game_count": len(games_upserted),
            "checkpoint_enabled": True,
            "legacy_state_fallback_used": bool(selection_meta.get("legacy_state_fallback_used")),
            "warning_reason_counts": warning_reason_counts,
            "skipped_files": [
                {"game_id": game_id, "source_key": source_key}
                for game_id, source_key in skipped
            ][:1000],
        },
    )
    audit_row = {
        "table_name": TABLE_NAME,
        "pipeline_run_id": pipeline_run_id,
        "run_status": run_status,
        "ingested_at_utc": ingested_at_utc,
        "source_bucket": S3_BUCKET,
        "source_prefix": SOURCE_PREFIX,
        "destination_prefix": DESTINATION_PREFIX,
        "process_all_files": int(PROCESS_ALL_FILES),
        "target_source_s3_path": TARGET_SOURCE_S3_PATH if not PROCESS_ALL_FILES else None,
        "incremental_mode": int(INCREMENTAL_MODE),
        "force_full_refresh": int(FORCE_FULL_REFRESH),
        "selection_mode": selection_meta.get("selection_mode"),
        "selection_watermark_utc": selection_meta.get("watermark_utc"),
        "selection_effective_watermark_utc": selection_meta.get("effective_watermark_utc"),
        "selection_lookback_minutes": selection_meta.get("lookback_minutes"),
        "selected_game_count": selection_meta.get("selected_game_count", len(keys)),
        "written_game_count": len(games_upserted),
        "target_game_ids": json.dumps(selection_meta.get("target_game_ids", []), sort_keys=True),
        "checkpoint_enabled": 1,
        "legacy_state_fallback_used": int(bool(selection_meta.get("legacy_state_fallback_used"))),
        "checkpoint_key": checkpoint_key_written,
        "files_selected": len(keys),
        "files_processed": total_files_processed,
        "games_upserted": len(games_upserted),
        "actions_processed": total_actions_processed,
        "rows_written": total_rows_written,
        "files_with_empty_actions": files_with_empty_actions,
        "skipped_file_count": len(skipped),
        "warning_count": warning_count,
        "error_count": 0,
        "details_key": details_key,
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
    print(f"Wrote audit JSON: s3://{S3_BUCKET}/{audit_json_key}")
    print(f"Wrote audit parquet: s3://{S3_BUCKET}/{audit_parquet_key}")

    state_after = {
        "table_name": TABLE_NAME,
        "updated_at_utc": state_datetime_to_iso(ingested_at_utc),
        "pipeline_run_id": pipeline_run_id,
        "max_source_last_modified_utc": state_datetime_to_iso(max_source_last_modified_seen),
        "files_selected": len(keys),
        "games_upserted": len(games_upserted),
        "previous_max_source_last_modified_utc": state_before.get("max_source_last_modified_utc"),
        "lookback_minutes": INCREMENTAL_LOOKBACK_MINUTES,
    }
    if PROCESS_ALL_FILES:
        write_state(s3_client, state_after)
        print(f"Wrote state: s3://{S3_BUCKET}/{STATE_KEY}")


if __name__ == "__main__":
    main()
