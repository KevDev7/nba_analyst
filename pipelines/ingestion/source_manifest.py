from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = (
    REPO_ROOT / "pipelines" / "athena" / "metadata" / "pipeline_registry.json"
)


SOURCE_FAMILY_BY_PREFIX = {
    "raw/cdn/": "cdn",
    "raw/scheduleleaguev2/": "nba_stats",
    "raw/boxscorematchupsv3/": "nba_stats",
    "raw/boxscoretraditionalv3/": "nba_stats",
    "raw/bball-reference/": "bbr",
    "raw/hoopR/": "hoopr",
    "raw/nba_data/": "nba_data",
}
DEFAULT_BACKFILL_SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
SEASON_SCOPED_MARKERS = ("game_id=", "<GAME_ID>", "season=", "season=*")


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def infer_source_family(destination_key: str) -> str:
    for prefix, family in SOURCE_FAMILY_BY_PREFIX.items():
        if destination_key.startswith(prefix):
            return family
    return "unknown"


def expected_backfill_seasons(destination_key: str) -> list[str]:
    if any(marker in destination_key for marker in SEASON_SCOPED_MARKERS):
        return list(DEFAULT_BACKFILL_SEASONS)
    return []


def build_source_manifest(registry: dict[str, Any]) -> dict[str, Any]:
    sources = []
    for artifact in registry["artifacts"]:
        if artifact["layer"] != "raw" or artifact["artifact_type"] != "source":
            continue
        destination_key = artifact["destination_key"]
        sources.append(
            {
                "id": artifact["id"],
                "name": artifact["name"],
                "source_family": infer_source_family(destination_key),
                "grain": artifact["grain"],
                "destination_key": destination_key,
                "entrypoint": artifact["entrypoint"],
                "dependencies": artifact["dependencies"],
                "raw_file_type": destination_key.rsplit(".", 1)[-1] if "." in destination_key else "prefix",
                "expected_backfill_seasons": expected_backfill_seasons(destination_key),
                "notes": artifact["notes"],
            }
        )

    return {
        "version": 1,
        "source_count": len(sources),
        "sources": sorted(sources, key=lambda source: source["id"]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the raw/bronze ingestion source manifest.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(json.dumps(build_source_manifest(load_registry(args.registry)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
