"""
Extract per-game parquet samples from the raw Kaggle PlayByPlay parquet.

Writes one local parquet file per requested game id so repeated comparisons do
not need to rescan the large source object each time.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.fs as fs
import pyarrow as pa
import pyarrow.parquet as pq


DEFAULT_SOURCE = "nba-analytics-lakehouse-dev/raw/kaggle/PlayByPlay.parquet"
DEFAULT_OUTPUT_DIR = (
    ""
    "pipelines/athena/metadata/kaggle_playbyplay_samples"
)


def normalize_kaggle_game_id(game_id: str) -> str:
    """Kaggle game ids are stored without leading zero padding."""
    return str(game_id).strip().lstrip("0")


def build_dataset(source_path: str) -> ds.Dataset:
    s3 = fs.S3FileSystem(region="us-east-1")
    return ds.dataset(source_path, filesystem=s3, format="parquet")


def build_filter(game_ids: list[str]) -> ds.Expression:
    """Build one OR filter for all requested Kaggle game ids."""
    expression = None
    for game_id in game_ids:
        current = ds.field("gameId") == game_id
        expression = current if expression is None else (expression | current)
    if expression is None:
        raise ValueError("No game ids supplied.")
    return expression


def extract_many(dataset: ds.Dataset, requested_game_ids: list[str], output_dir: Path) -> list[tuple[str, str, int, Path]]:
    kaggle_game_ids = [normalize_kaggle_game_id(game_id) for game_id in requested_game_ids]
    filtered = dataset.to_table(filter=build_filter(kaggle_game_ids))

    results: list[tuple[str, str, int, Path]] = []
    grouped: dict[str, list[int]] = {}
    game_id_column = filtered.column("gameId").to_pylist() if filtered.num_rows > 0 else []
    for index, kaggle_game_id in enumerate(game_id_column):
        grouped.setdefault(str(kaggle_game_id), []).append(index)

    for requested_game_id, kaggle_game_id in zip(requested_game_ids, kaggle_game_ids):
        indices = grouped.get(kaggle_game_id, [])
        if indices:
            table = filtered.take(pa.array(indices, type=pa.int64()))
        else:
            table = filtered.slice(0, 0)
        output_path = output_dir / f"game_id={requested_game_id}.parquet"
        pq.write_table(table, output_path, compression="snappy")
        results.append((requested_game_id, kaggle_game_id, table.num_rows, output_path))
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--game-ids",
        required=True,
        help="Comma-separated canonical game ids, e.g. 0022400524,0022400532",
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="S3 path to the raw Kaggle PlayByPlay parquet",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Local output directory for extracted parquet samples",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    game_ids = [part.strip() for part in args.game_ids.split(",") if part.strip()]
    dataset = build_dataset(args.source)

    for requested_game_id, kaggle_game_id, row_count, output_path in extract_many(
        dataset, game_ids, output_dir
    ):
        print(
            {
                "requested_game_id": requested_game_id,
                "kaggle_game_id": kaggle_game_id,
                "row_count": row_count,
                "output_path": str(output_path),
            }
        )


if __name__ == "__main__":
    main()
