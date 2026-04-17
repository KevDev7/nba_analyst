from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pyarrow as pa

from pipelines.athena.transform.silver.bbr import BbrPlayerEnrichmentPipeline

try:
    from ..gold_transform_helpers import to_positive_int_or_none
except ImportError:
    from gold_transform_helpers import to_positive_int_or_none  # type: ignore[no-redef]


def build_bbr_by_person_id(
    bridge_table: pa.Table,
    bbr_profile_table: pa.Table,
) -> dict[int, dict[str, Any]]:
    person_ids = {
        person_id
        for row in bridge_table.to_pylist()
        if (person_id := to_positive_int_or_none(row.get("nba_person_id"))) is not None
    }
    pipeline = BbrPlayerEnrichmentPipeline(
        accepted_bridge_rows=bridge_table.to_pylist(),
        profile_rows=bbr_profile_table.to_pylist(),
    )
    return {
        person_id: asdict(profile)
        for person_id, profile in pipeline.build_current_gold_profiles(person_ids).items()
    }
