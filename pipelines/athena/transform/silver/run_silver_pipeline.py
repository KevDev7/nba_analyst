"""Run Silver Wave 2/3 transforms end-to-end with consolidated status output."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScriptResult:
    script: str
    returncode: int
    duration_seconds: float
    attempts: int
    timed_out: bool


def run_script(
    script_path: Path,
    retries: int,
    timeout_seconds: int,
    retry_backoff_seconds: int,
) -> ScriptResult:
    """Execute one script with retries, optional timeout, and streamed stdout/stderr."""
    attempts = 0
    total_duration = 0.0
    final_returncode = 1
    timed_out = False

    while attempts <= retries:
        attempts += 1
        print(f"\n=== Running {script_path.name} (attempt {attempts}/{retries + 1}) ===")
        start = time.time()
        timed_out = False

        try:
            completed = subprocess.run(
                [sys.executable, "-u", str(script_path)],
                check=False,
                timeout=(None if timeout_seconds <= 0 else timeout_seconds),
            )
            final_returncode = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            final_returncode = 124
            print(
                f"Script timed out after {timeout_seconds}s: {script_path.name}"
            )

        duration = time.time() - start
        total_duration += duration
        print(
            f"=== Finished {script_path.name} rc={final_returncode} "
            f"duration={duration:.1f}s (attempt {attempts}) ==="
        )

        if final_returncode == 0:
            break

        if attempts <= retries:
            sleep_seconds = retry_backoff_seconds * attempts
            print(
                f"Retrying {script_path.name} in {sleep_seconds}s "
                f"(attempt {attempts + 1}/{retries + 1})"
            )
            time.sleep(sleep_seconds)

    return ScriptResult(
        script=script_path.name,
        returncode=final_returncode,
        duration_seconds=total_duration,
        attempts=attempts,
        timed_out=timed_out,
    )


def parse_only_list(value: str | None) -> set[str]:
    """Parse comma-separated script names to run."""
    if value is None or value.strip() == "":
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Silver Wave 2/3 transforms")
    parser.add_argument(
        "--include-heavy",
        action="store_true",
        help="Include high-volume per-game transforms (playbyplay + pbpstats sidecars + on_court_state).",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue running remaining scripts after a failure.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Retry count per script on non-zero exit (default: 1).",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=int,
        default=15,
        help="Base backoff seconds between retries (default: 15).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=0,
        help="Per-script timeout seconds. 0 disables timeout (default: 0).",
    )
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated list of script filenames to run (targeted rerun/backfill).",
    )
    parser.add_argument(
        "--skip-reconciliation",
        action="store_true",
        help="Skip validate_silver_reconciliation.py at end of run.",
    )
    args = parser.parse_args()

    if args.retries < 0:
        raise SystemExit("--retries must be >= 0")
    if args.retry_backoff_seconds < 0:
        raise SystemExit("--retry-backoff-seconds must be >= 0")

    base_dir = Path(__file__).resolve().parent
    scripts = [
        base_dir / "build_silver_players.py",
        base_dir / "build_silver_team_histories.py",
        base_dir / "build_silver_player_movement.py",
        base_dir / "build_silver_schedule.py",
        base_dir / "build_silver_boxscore_game.py",
        base_dir / "build_silver_boxscore_player_game.py",
        base_dir / "build_silver_boxscore_team_game.py",
        base_dir / "build_silver_boxscore_game_official.py",
        base_dir / "build_silver_boxscore_team_period.py",
    ]
    if args.include_heavy:
        scripts.extend(
            [
                base_dir / "build_silver_playbyplay_events.py",
                base_dir / "build_silver_pbpstats_event_projection_v1.py",
                base_dir / "build_silver_event_projection_v2.py",
                base_dir / "build_silver_pbpstats_event_context_v1.py",
                base_dir / "build_silver_on_court_state.py",
                base_dir / "build_silver_possessions.py",
                base_dir / "build_silver_possessions_ot_fallback.py",
                base_dir / "build_silver_player_game_possession_context.py",
                base_dir / "build_silver_player_game_defensive_shot_context.py",
                base_dir / "build_silver_player_game_opportunity_context.py",
                base_dir / "build_silver_team_game_possession_context.py",
                base_dir / "build_silver_team_game_defensive_shot_context.py",
            ]
        )
    if not args.skip_reconciliation:
        scripts.append(base_dir / "validate_silver_reconciliation.py")

    only = parse_only_list(args.only)
    if only:
        scripts = [path for path in scripts if path.name in only]
        missing_from_only = sorted(name for name in only if not (base_dir / name).exists())
        if missing_from_only:
            print("Unknown scripts in --only:")
            for name in missing_from_only:
                print(f"- {name}")
            raise SystemExit(2)
        if not scripts:
            raise SystemExit("No scripts selected after --only filtering.")

    missing_scripts = [str(path) for path in scripts if not path.exists()]
    if missing_scripts:
        print("Missing scripts:")
        for path in missing_scripts:
            print(f"- {path}")
        raise SystemExit(2)

    print("Pipeline settings:")
    print(f"- include_heavy={args.include_heavy}")
    print(f"- continue_on_error={args.continue_on_error}")
    print(f"- retries={args.retries}")
    print(f"- retry_backoff_seconds={args.retry_backoff_seconds}")
    print(f"- timeout_seconds={args.timeout_seconds}")
    print(f"- skip_reconciliation={args.skip_reconciliation}")
    print(f"- scripts={len(scripts)}")

    overall_start = time.time()
    results: list[ScriptResult] = []

    for script_path in scripts:
        result = run_script(
            script_path,
            retries=args.retries,
            timeout_seconds=args.timeout_seconds,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )
        results.append(result)

        if result.returncode != 0 and not args.continue_on_error:
            break

    total_duration = time.time() - overall_start
    failures = [r for r in results if r.returncode != 0]

    print("\n=== Silver Pipeline Summary ===")
    for result in results:
        print(
            f"{result.script}: rc={result.returncode} attempts={result.attempts} "
            f"timed_out={int(result.timed_out)} duration={result.duration_seconds:.1f}s"
        )
    print(f"Total duration: {total_duration:.1f}s")
    print(f"Failures: {len(failures)}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
