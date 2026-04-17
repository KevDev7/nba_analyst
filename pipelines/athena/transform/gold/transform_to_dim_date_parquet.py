"""
Build gold dim_date as a Type-1 calendar dimension from silver game dates.

Reads:
  s3://nba-analytics-lakehouse-dev/silver/scheduleLeagueV2_1.parquet
  s3://nba-analytics-lakehouse-dev/silver/boxscore_game.parquet

Writes (full overwrite):
  s3://nba-analytics-lakehouse-dev/gold/dim_date/dim_date.parquet
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import boto3
import pyarrow as pa
from dotenv import load_dotenv

try:
    from .gold_transform_helpers import (
        S3_BUCKET,
        best_row,
        localized_date_from_timestamp,
        parse_date_or_none,
        parse_game_code_date,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        to_str_or_none,
        to_positive_int_or_none,
        write_parquet_to_s3,
    )
except ImportError:
    from gold_transform_helpers import (  # type: ignore[no-redef]
        S3_BUCKET,
        best_row,
        localized_date_from_timestamp,
        parse_date_or_none,
        parse_game_code_date,
        parse_timestamp_utc,
        read_parquet_table_from_s3,
        to_str_or_none,
        to_positive_int_or_none,
        write_parquet_to_s3,
    )

load_dotenv(override=True)

SCHEDULE_SOURCE_KEY = "silver/scheduleLeagueV2_1.parquet"
BOXSCORE_SOURCE_KEY = "silver/boxscore_game.parquet"
DESTINATION_KEY = "gold/dim_date/dim_date.parquet"

SCHEDULE_REQUIRED_COLUMNS = [
    "gameDate",
    "gameDateTimeUTC",
    "gameCode",
    "weekNumber",
    "weekName",
]

BOXSCORE_REQUIRED_COLUMNS = ["gameCode", "gameTimeHome", "gameTimeUTC", "arenaTimezone"]

TARGET_SCHEMA = pa.schema(
    [
        pa.field("date_sk", pa.int64()),
        pa.field("calendar_date", pa.date32()),
        pa.field("day_of_week_iso", pa.int64()),
        pa.field("day_name", pa.string()),
        pa.field("day_of_month", pa.int64()),
        pa.field("day_of_year", pa.int64()),
        pa.field("week_of_year", pa.int64()),
        pa.field("month_num", pa.int64()),
        pa.field("month_name", pa.string()),
        pa.field("quarter_num", pa.int64()),
        pa.field("year_num", pa.int64()),
        pa.field("nba_week_number", pa.int64()),
        pa.field("nba_week_name", pa.string()),
        pa.field("is_weekend", pa.bool_()),
        pa.field("is_month_start", pa.bool_()),
        pa.field("is_month_end", pa.bool_()),
        pa.field("is_quarter_start", pa.bool_()),
        pa.field("is_quarter_end", pa.bool_()),
        pa.field("is_year_start", pa.bool_()),
        pa.field("is_year_end", pa.bool_()),
        pa.field("created_at_utc", pa.timestamp("us", tz="UTC")),
        pa.field("updated_at_utc", pa.timestamp("us", tz="UTC")),
    ]
)


def build_schedule_context(schedule_table: pa.Table) -> dict[date, dict[str, Any]]:
    context_by_date: dict[date, dict[str, Any]] = {}
    for row in schedule_table.to_pylist():
        schedule_date = parse_date_or_none(row.get("gameDate"))
        schedule_dt = parse_timestamp_utc(row.get("gameDateTimeUTC"))
        event_date = schedule_date or parse_game_code_date(row.get("gameCode")) or (
            schedule_dt.date() if schedule_dt is not None else None
        )
        if event_date is None:
            continue

        candidate = {
            "calendar_date": event_date,
            "nba_week_number": to_positive_int_or_none(row.get("weekNumber")),
            "nba_week_name": to_str_or_none(row.get("weekName")),
        }
        if candidate["nba_week_number"] is None:
            candidate["nba_week_name"] = None

        context_by_date[event_date] = best_row(
            context_by_date.get(event_date),
            candidate,
            quality_keys=["nba_week_number", "nba_week_name"],
        )
    return context_by_date


def build_calendar_dates(schedule_table: pa.Table, boxscore_table: pa.Table) -> tuple[set[date], dict[date, dict[str, Any]]]:
    calendar_dates: set[date] = set()
    schedule_context = build_schedule_context(schedule_table)
    calendar_dates.update(schedule_context.keys())

    for row in boxscore_table.to_pylist():
        game_date = (
            parse_game_code_date(row.get("gameCode"))
            or localized_date_from_timestamp(row.get("gameTimeHome"), row.get("arenaTimezone"))
            or localized_date_from_timestamp(row.get("gameTimeUTC"), row.get("arenaTimezone"))
            or parse_date_or_none(row.get("gameTimeUTC"))
        )
        if game_date is not None:
            calendar_dates.add(game_date)
    return calendar_dates, schedule_context


def build_dim_date_rows(calendar_dates: set[date], schedule_context: dict[date, dict[str, Any]]) -> list[dict[str, Any]]:
    run_ts = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []

    for current_date in sorted(calendar_dates):
        context = schedule_context.get(current_date, {})
        next_day = current_date + timedelta(days=1)
        month_end = next_day.month != current_date.month
        quarter_end = (next_day.month - 1) // 3 != (current_date.month - 1) // 3
        # Match the Databricks sentinel-row contract for 0001-01-01.
        year_end = None if current_date == date.min else next_day.year != current_date.year

        rows.append(
            {
                "date_sk": int(current_date.strftime("%Y%m%d")),
                "calendar_date": current_date,
                "day_of_week_iso": current_date.isoweekday(),
                "day_name": current_date.strftime("%A"),
                "day_of_month": current_date.day,
                "day_of_year": current_date.timetuple().tm_yday,
                "week_of_year": current_date.isocalendar().week,
                "month_num": current_date.month,
                "month_name": current_date.strftime("%B"),
                "quarter_num": ((current_date.month - 1) // 3) + 1,
                "year_num": current_date.year,
                "nba_week_number": context.get("nba_week_number"),
                "nba_week_name": context.get("nba_week_name"),
                "is_weekend": current_date.isoweekday() >= 6,
                "is_month_start": current_date.day == 1,
                "is_month_end": month_end,
                "is_quarter_start": current_date.day == 1 and current_date.month in {1, 4, 7, 10},
                "is_quarter_end": quarter_end,
                "is_year_start": current_date.month == 1 and current_date.day == 1,
                "is_year_end": year_end,
                "created_at_utc": run_ts,
                "updated_at_utc": run_ts,
            }
        )

    return rows


def main() -> None:
    s3_client = boto3.client("s3")

    schedule_table = read_parquet_table_from_s3(s3_client, SCHEDULE_SOURCE_KEY, SCHEDULE_REQUIRED_COLUMNS)
    boxscore_table = read_parquet_table_from_s3(s3_client, BOXSCORE_SOURCE_KEY, BOXSCORE_REQUIRED_COLUMNS)

    calendar_dates, schedule_context = build_calendar_dates(schedule_table, boxscore_table)
    rows = build_dim_date_rows(calendar_dates, schedule_context)

    write_parquet_to_s3(rows, TARGET_SCHEMA, DESTINATION_KEY, s3_client)
    print(f"Wrote s3://{S3_BUCKET}/{DESTINATION_KEY}")


if __name__ == "__main__":
    main()
