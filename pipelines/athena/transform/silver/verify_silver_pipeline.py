"""Wave 3 verification checks for Silver scripts (compile, smoke, audit contracts)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import boto3

BASE_DIR = Path(__file__).resolve().parent
S3_BUCKET = "nba-analytics-lakehouse-dev"


def run_command(command: list[str]) -> None:
    """Run a command and raise when non-zero."""
    print(f"$ {' '.join(command)}")
    subprocess.run(command, check=True)


def compile_check() -> None:
    """Compile all silver python scripts."""
    scripts = sorted(str(path) for path in BASE_DIR.glob("*.py"))
    run_command([sys.executable, "-m", "py_compile", *scripts])
    print("Compile check passed")


def smoke_check() -> None:
    """Run quick smoke transforms without full-history heavy scans."""
    orchestrator = str(BASE_DIR / "run_silver_pipeline.py")
    only_scripts = ",".join(
        [
            "build_silver_players.py",
            "build_silver_team_histories.py",
            "build_silver_player_movement.py",
            "build_silver_schedule.py",
        ]
    )
    run_command(
        [
            sys.executable,
            "-u",
            orchestrator,
            "--only",
            only_scripts,
            "--skip-reconciliation",
            "--retries",
            "0",
        ]
    )

    playbyplay_smoke = (
        "import sys; "
        f"sys.path.append('{BASE_DIR}'); "
        "import build_silver_playbyplay_events as m; "
        "m.PROCESS_ALL_FILES=False; "
        "m.TARGET_SOURCE_S3_PATH='s3://nba-analytics-lakehouse-dev/raw/cdn/playbyplay/game_id=22000517.json'; "
        "m.main()"
    )
    run_command([sys.executable, "-c", playbyplay_smoke])

    on_court_smoke = (
        "import sys; "
        f"sys.path.append('{BASE_DIR}'); "
        "import build_silver_on_court_state as m; "
        "m.PROCESS_ALL_FILES=False; "
        "m.TARGET_PLAYBYPLAY_S3_PATH='s3://nba-analytics-lakehouse-dev/silver/playbyplay/game_id=0022000517.parquet'; "
        "m.main()"
    )
    run_command([sys.executable, "-c", on_court_smoke])
    print("Smoke check passed")


def latest_audit_key(s3_client, table_name: str) -> str:
    """Get the latest audit JSON key for a table."""
    prefix = f"silver/_audit/{table_name}/"
    response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=prefix)
    candidates = [
        obj
        for obj in response.get("Contents", [])
        if obj["Key"].endswith(".json") and not obj["Key"].endswith("_details.json")
    ]
    if not candidates:
        raise RuntimeError(f"No audit JSON found for table={table_name}")
    latest = max(candidates, key=lambda x: x["LastModified"])
    return latest["Key"]


def audit_contract_check() -> None:
    """Validate required fields exist on latest audit rows."""
    s3_client = boto3.client("s3")
    tables = [
        "players",
        "team_histories",
        "player_movement",
        "scheduleLeagueV2_1",
        "boxscore_game",
        "boxscore_player_game",
        "boxscore_team_game",
        "boxscore_game_official",
        "boxscore_team_period",
        "playbyplay_events",
        "on_court_state",
        "silver_reconciliation",
    ]
    required_fields = [
        "table_name",
        "pipeline_run_id",
        "run_status",
        "ingested_at_utc",
        "warning_count",
        "error_count",
        "warning_reason_counts",
        "error_reason_counts",
    ]

    for table_name in tables:
        key = latest_audit_key(s3_client, table_name)
        payload = s3_client.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
        row = json.loads(payload)
        missing = [field for field in required_fields if field not in row]
        if missing:
            raise RuntimeError(
                f"Audit contract failed for {table_name}, missing fields: {missing}"
            )
        print(f"Audit contract OK: {table_name} ({key})")

    print("Audit contract check passed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Silver Wave 3 readiness")
    parser.add_argument("--skip-compile", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--skip-audit", action="store_true")
    args = parser.parse_args()

    if not args.skip_compile:
        compile_check()
    if not args.skip_smoke:
        smoke_check()
    if not args.skip_audit:
        audit_contract_check()

    print("Wave 3 verification complete")


if __name__ == "__main__":
    main()
