from __future__ import annotations

from typing import Any

try:
    from pipelines.athena.quality.deploy_quality_tables import (
        QUALITY_DATABASE,
        deploy_quality_tables,
    )
    from pipelines.athena.quality.quality_manifest import DEFAULT_BUCKET
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipelines.athena.quality.deploy_quality_tables import (
        QUALITY_DATABASE,
        deploy_quality_tables,
    )
    from pipelines.athena.quality.quality_manifest import DEFAULT_BUCKET


def refresh_quality_athena_tables(
    *,
    bucket: str = DEFAULT_BUCKET,
    database: str = QUALITY_DATABASE,
) -> dict[str, Any]:
    """Create queryable quality tables and refresh discovered run_date partitions."""
    return deploy_quality_tables(
        bucket=bucket,
        database=database,
        drop_existing=False,
    )
