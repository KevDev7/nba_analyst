from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = (
    REPO_ROOT / "pipelines" / "athena" / "metadata" / "pipeline_registry.json"
)
DEFAULT_BUCKET = "nba-analytics-lakehouse-dev"
QUALITY_ROOT_PREFIX = "quality"

QUALITY_DATASETS = {
    "pipeline_runs": "One row per observed pipeline entrypoint run.",
    "table_profiles": "Row counts and null profiles by table artifact.",
    "schema_snapshots": "Column/type snapshots by table artifact and run.",
    "grain_checks": "Duplicate-key checks for artifacts with known grain columns.",
    "reconciliation": "Cross-table consistency summaries.",
    "source_completeness": "Source expected-vs-observed completeness summaries.",
    "quarantine_summaries": "Counts and reason summaries for quarantine outputs.",
    "row_count_trends": "Current-vs-prior row-count trend summaries.",
    "schema_drift": "Current schema compared with the previous schema snapshot.",
    "anomaly_summaries": "Layer-level anomalies emitted from quality checks.",
    "serving_snapshot_quality": "Serving snapshot coverage and freshness summaries.",
}

KNOWN_GRAIN_COLUMNS = {
    "silver.players": ["personId"],
    "silver.team_histories": ["teamId", "seasonFounded"],
    "silver.player_movement": [
        "Transaction_Type",
        "TRANSACTION_DATE",
        "TRANSACTION_DESCRIPTION",
        "TEAM_ID",
        "TEAM_SLUG",
        "PLAYER_ID",
        "Additional_Sort",
        "GroupSort",
    ],
    "silver.scheduleLeagueV2_1": ["gameId"],
    "silver.boxscore_game": ["gameId"],
    "silver.boxscore_player_game": ["gameId", "personId"],
    "silver.boxscore_team_game": ["gameId", "team_side"],
    "silver.boxscore_game_official": ["gameId", "personId"],
    "silver.boxscore_team_period": ["gameId", "team_side", "period_number"],
    "silver.boxscore_matchups": ["game_id", "team_id", "person_id", "matchups_person_id"],
    "silver.playbyplay": ["gameId", "actionNumber"],
    "silver.shot_location_events": ["game_id", "action_number"],
    "silver.pbpstats_event_projection_v1": ["game_id", "event_num"],
    "silver.event_projection_v2": ["game_id", "event_num"],
    "silver.pbpstats_event_context_v1": ["game_id", "event_num"],
    "silver.on_court_state": ["gameId", "period", "stint_id"],
    "silver.possessions": ["gameId", "possessionNumber"],
    "silver.possessions_ot_fallback": ["gameId", "possessionNumber"],
    "silver.player_game_possession_context": ["game_id", "person_id"],
    "silver.player_game_defensive_shot_context": ["game_id", "person_id"],
    "silver.player_game_opportunity_context": ["game_id", "person_id"],
    "silver.team_game_possession_context": ["game_id", "team_id"],
    "silver.team_game_defensive_shot_context": ["game_id", "team_id"],
    "silver.bbr_player_index": ["basketball_reference_player_id"],
    "silver.bbr_player_profile": ["basketball_reference_player_id"],
    "silver.bbr_player_awards": ["basketball_reference_player_id", "award_family", "season_label"],
    "silver.player_identity_bridge_bbr_nba": ["basketball_reference_player_id", "nba_person_id"],
    "legacy_gold.dim_date": ["date_sk"],
    "legacy_gold.dim_game": ["game_sk"],
    "legacy_gold.dim_team": ["team_sk"],
    "legacy_gold.dim_player": ["player_sk"],
    "legacy_gold.extended_player_dim": ["person_id"],
    "legacy_gold.fct_team_game": ["game_id", "team_id"],
    "legacy_gold.fct_player_game": ["game_id", "person_id"],
    "legacy_gold.agg_player_season": ["person_id", "season_year", "season_type"],
    "legacy_gold.agg_team_season": ["team_id", "season_year", "season_type"],
    "semantic_gold.player": ["person_id"],
    "semantic_gold.team": ["team_id"],
    "semantic_gold.arena": ["arena_id"],
    "semantic_gold.game": ["game_id"],
    "semantic_gold.player_game": ["game_id", "person_id"],
    "semantic_gold.team_game": ["game_id", "team_id"],
    "semantic_gold.player_season": ["person_id", "season_year", "season_type"],
    "semantic_gold.player_season_team": ["person_id", "team_id", "season_year", "season_type"],
    "semantic_gold.team_season": ["team_id", "season_year", "season_type"],
}

RECONCILIATION_CHECKS = [
    {
        "check_id": "silver.boxscore_game_children_reference_parent",
        "dataset": "reconciliation",
        "artifact_id": "silver.boxscore_game",
        "depends_on": [
            "silver.boxscore_game",
            "silver.boxscore_player_game",
            "silver.boxscore_team_game",
        ],
        "description": "Player-game and team-game rows should reference known boxscore game IDs.",
    },
    {
        "check_id": "silver.boxscore_team_game_has_home_and_away",
        "dataset": "reconciliation",
        "artifact_id": "silver.boxscore_team_game",
        "depends_on": ["silver.boxscore_team_game"],
        "description": "Each boxscore team game should have exactly one home and one away row per game.",
    },
]


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def today_run_date() -> str:
    return date.today().isoformat()


def new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"quality_baseline_{timestamp}_{uuid.uuid4().hex[:8]}"


def quality_result_key(dataset: str, artifact_id: str, run_date: str, run_id: str) -> str:
    artifact_partition = artifact_id.replace(".", "/")
    return (
        f"{QUALITY_ROOT_PREFIX}/{dataset}/{artifact_partition}/"
        f"run_date={run_date}/{run_id}.parquet"
    )


def manifest_key(run_date: str, run_id: str) -> str:
    return f"{QUALITY_ROOT_PREFIX}/pipeline_runs/run_date={run_date}/{run_id}.json"


def _profile_checks_for_artifact(
    artifact: dict[str, Any], *, run_date: str, run_id: str
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    artifact_type = artifact["artifact_type"]
    if artifact_type not in {"table", "artifact"}:
        return checks

    for dataset in ("table_profiles", "schema_snapshots"):
        checks.append(
            {
                "check_id": f"{artifact['id']}.{dataset}",
                "dataset": dataset,
                "artifact_id": artifact["id"],
                "layer": artifact["layer"],
                "source_key": artifact["destination_key"],
                "result_key": quality_result_key(dataset, artifact["id"], run_date, run_id),
                "status": "planned",
            }
        )

    for dataset in ("row_count_trends", "schema_drift"):
        checks.append(
            {
                "check_id": f"{artifact['id']}.{dataset}",
                "dataset": dataset,
                "artifact_id": artifact["id"],
                "layer": artifact["layer"],
                "source_key": artifact["destination_key"],
                "result_key": quality_result_key(dataset, artifact["id"], run_date, run_id),
                "status": "planned",
            }
        )

    grain_columns = KNOWN_GRAIN_COLUMNS.get(artifact["id"])
    if grain_columns:
        checks.append(
            {
                "check_id": f"{artifact['id']}.grain_duplicates",
                "dataset": "grain_checks",
                "artifact_id": artifact["id"],
                "layer": artifact["layer"],
                "source_key": artifact["destination_key"],
                "grain_columns": grain_columns,
                "result_key": quality_result_key("grain_checks", artifact["id"], run_date, run_id),
                "status": "planned",
            }
        )

    if artifact["layer"] == "silver":
        checks.append(
            {
                "check_id": f"{artifact['id']}.quarantine_summary",
                "dataset": "quarantine_summaries",
                "artifact_id": artifact["id"],
                "layer": artifact["layer"],
                "source_key": f"silver/_quarantine/{artifact['name']}/",
                "result_key": quality_result_key(
                    "quarantine_summaries", artifact["id"], run_date, run_id
                ),
                "status": "planned",
            }
        )

    if artifact["layer"] == "serving":
        checks.append(
            {
                "check_id": f"{artifact['id']}.serving_snapshot_quality",
                "dataset": "serving_snapshot_quality",
                "artifact_id": artifact["id"],
                "layer": artifact["layer"],
                "source_key": artifact["destination_key"],
                "result_key": quality_result_key(
                    "serving_snapshot_quality", artifact["id"], run_date, run_id
                ),
                "status": "planned",
            }
        )

    return checks


def _source_completeness_check(
    artifact: dict[str, Any], *, run_date: str, run_id: str
) -> dict[str, Any] | None:
    if artifact["layer"] != "raw" or artifact["artifact_type"] != "source":
        return None
    return {
        "check_id": f"{artifact['id']}.source_completeness",
        "dataset": "source_completeness",
        "artifact_id": artifact["id"],
        "layer": artifact["layer"],
        "source_key": artifact["destination_key"],
        "result_key": quality_result_key("source_completeness", artifact["id"], run_date, run_id),
        "status": "planned",
    }


def build_quality_manifest(
    registry: dict[str, Any], *, run_id: str | None = None, run_date: str | None = None
) -> dict[str, Any]:
    resolved_run_id = run_id or new_run_id()
    resolved_run_date = run_date or today_run_date()
    artifacts = registry["artifacts"]

    checks: list[dict[str, Any]] = [
        {
            "check_id": "pipeline.registry_snapshot",
            "dataset": "pipeline_runs",
            "artifact_id": "pipeline.registry",
            "layer": "quality",
            "source_key": "pipelines/athena/metadata/pipeline_registry.json",
            "result_key": manifest_key(resolved_run_date, resolved_run_id),
            "status": "planned",
        }
    ]

    for layer in ("raw", "silver", "legacy_gold", "semantic_gold", "serving"):
        checks.append(
            {
                "check_id": f"{layer}.anomaly_summary",
                "dataset": "anomaly_summaries",
                "artifact_id": f"{layer}.*",
                "layer": layer,
                "source_key": None,
                "result_key": quality_result_key(
                    "anomaly_summaries", f"{layer}.all", resolved_run_date, resolved_run_id
                ),
                "status": "planned",
            }
        )

    for artifact in artifacts:
        source_check = _source_completeness_check(
            artifact, run_date=resolved_run_date, run_id=resolved_run_id
        )
        if source_check:
            checks.append(source_check)
        checks.extend(
            _profile_checks_for_artifact(
                artifact, run_date=resolved_run_date, run_id=resolved_run_id
            )
        )

    known_artifact_ids = {artifact["id"] for artifact in artifacts}
    for check in RECONCILIATION_CHECKS:
        if all(dependency in known_artifact_ids for dependency in check["depends_on"]):
            checks.append(
                {
                    **check,
                    "layer": "quality",
                    "source_key": None,
                    "result_key": quality_result_key(
                        check["dataset"], check["check_id"], resolved_run_date, resolved_run_id
                    ),
                    "status": "planned",
                }
            )

    return {
        "version": 1,
        "run_id": resolved_run_id,
        "run_date": resolved_run_date,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "quality_root_prefix": QUALITY_ROOT_PREFIX,
        "registry_status": registry["status"],
        "datasets": QUALITY_DATASETS,
        "artifact_count": len(artifacts),
        "check_count": len(checks),
        "checks": checks,
    }


def write_manifest_local(manifest: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_manifest_s3(
    manifest: dict[str, Any], *, bucket: str = DEFAULT_BUCKET, key: str | None = None
) -> str:
    import boto3

    resolved_key = key or manifest_key(manifest["run_date"], manifest["run_id"])
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=resolved_key,
        Body=json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )
    return resolved_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the registry-driven quality baseline manifest.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-date", default="")
    parser.add_argument("--output-local", type=Path)
    parser.add_argument("--write-s3", action="store_true")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--s3-key", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_quality_manifest(
        load_registry(args.registry),
        run_id=args.run_id or None,
        run_date=args.run_date or None,
    )

    if args.output_local:
        write_manifest_local(manifest, args.output_local)
        print(f"Wrote local quality manifest: {args.output_local}")
    else:
        print(json.dumps(manifest, indent=2, sort_keys=True))

    if args.write_s3:
        key = write_manifest_s3(
            manifest,
            bucket=args.bucket,
            key=args.s3_key or None,
        )
        print(f"Wrote S3 quality manifest: s3://{args.bucket}/{key}")


if __name__ == "__main__":
    main()
