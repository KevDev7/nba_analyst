from __future__ import annotations

from dataclasses import asdict
from typing import Any

import boto3

from .artifacts import build_identity_artifacts
from .awards_parser import build_award_artifacts
from .gold_projection import build_current_gold_profiles as project_current_gold_profiles
from .index_parser import SOURCE_PREFIX as INDEX_SOURCE_PREFIX
from .index_parser import build_index_artifacts, parse_source_key as parse_index_source_key
from .profile_parser import SOURCE_PREFIX as PROFILE_SOURCE_PREFIX
from .profile_parser import build_profile_artifacts, parse_source_key as parse_profile_source_key
from .sources import load_latest_raw_snapshots, read_parquet_rows
from .types import BbrGoldProfile, BbrSilverArtifacts, RawHtmlSnapshot


S3_BUCKET = "nba-analytics-lakehouse-dev"
NBA_SOURCE_KEY = "silver/players.parquet"
ACCEPTED_BRIDGE_SOURCE_KEY = "silver/player_identity_bridge_bbr_nba.parquet"
PROFILE_SOURCE_KEY = "silver/bbr_player_profile.parquet"


class BbrPlayerEnrichmentPipeline:
    def __init__(
        self,
        *,
        s3_client=None,
        raw_index_snapshots: list[RawHtmlSnapshot] | None = None,
        raw_profile_snapshots: list[RawHtmlSnapshot] | None = None,
        nba_player_rows: list[dict[str, Any]] | None = None,
        accepted_bridge_rows: list[dict[str, Any]] | None = None,
        profile_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.s3_client = s3_client
        self._raw_index_snapshots = raw_index_snapshots
        self._raw_profile_snapshots = raw_profile_snapshots
        self._nba_player_rows = nba_player_rows
        self._accepted_bridge_rows = accepted_bridge_rows
        self._profile_rows = profile_rows
        self._silver_artifacts: BbrSilverArtifacts | None = None

    def _get_s3_client(self):
        if self.s3_client is None:
            self.s3_client = boto3.client("s3")
        return self.s3_client

    def _load_raw_index_snapshots(self) -> list[RawHtmlSnapshot]:
        if self._raw_index_snapshots is not None:
            return self._raw_index_snapshots
        return load_latest_raw_snapshots(
            self._get_s3_client(),
            bucket=S3_BUCKET,
            prefix=INDEX_SOURCE_PREFIX,
            key_parser=parse_index_source_key,
        )

    def _load_raw_profile_snapshots(self) -> list[RawHtmlSnapshot]:
        if self._raw_profile_snapshots is not None:
            return self._raw_profile_snapshots
        return load_latest_raw_snapshots(
            self._get_s3_client(),
            bucket=S3_BUCKET,
            prefix=PROFILE_SOURCE_PREFIX,
            key_parser=parse_profile_source_key,
        )

    def _load_nba_player_rows(self) -> list[dict[str, Any]]:
        if self._nba_player_rows is not None:
            return self._nba_player_rows
        return read_parquet_rows(self._get_s3_client(), bucket=S3_BUCKET, key=NBA_SOURCE_KEY)

    def _load_accepted_bridge_rows(self) -> list[dict[str, Any]]:
        if self._accepted_bridge_rows is not None:
            return self._accepted_bridge_rows
        if self._silver_artifacts is not None:
            return self._silver_artifacts.accepted_bridge_rows
        return read_parquet_rows(self._get_s3_client(), bucket=S3_BUCKET, key=ACCEPTED_BRIDGE_SOURCE_KEY)

    def _load_profile_rows(self) -> list[dict[str, Any]]:
        if self._profile_rows is not None:
            return self._profile_rows
        if self._silver_artifacts is not None:
            return self._silver_artifacts.profile_rows
        return read_parquet_rows(self._get_s3_client(), bucket=S3_BUCKET, key=PROFILE_SOURCE_KEY)

    def build_silver_artifacts(self) -> BbrSilverArtifacts:
        if self._silver_artifacts is not None:
            return self._silver_artifacts
        raw_profile_snapshots = self._load_raw_profile_snapshots()
        index_rows, index_quarantine_rows, index_duplicate_count, index_parse_failures = build_index_artifacts(
            self._load_raw_index_snapshots()
        )
        profile_rows, profile_parse_failures, profile_warning_reason_counts = build_profile_artifacts(raw_profile_snapshots)
        awards_rows, awards_parse_failures, awards_warning_reason_counts = build_award_artifacts(raw_profile_snapshots)
        identity_artifacts = build_identity_artifacts(self._load_nba_player_rows(), profile_rows)
        self._silver_artifacts = BbrSilverArtifacts(
            index_rows=index_rows,
            index_quarantine_rows=index_quarantine_rows,
            profile_rows=profile_rows,
            awards_rows=awards_rows,
            accepted_bridge_rows=identity_artifacts["accepted_bridge_rows"],
            duplicate_nba_rows=identity_artifacts["duplicate_nba_rows"],
            ambiguous_rows=identity_artifacts["ambiguous_rows"],
            unmatched_nba_rows=identity_artifacts["unmatched_nba_rows"],
            unmatched_bbr_rows=identity_artifacts["unmatched_bbr_rows"],
            index_duplicate_count=index_duplicate_count,
            index_parse_failures=index_parse_failures,
            profile_parse_failures=profile_parse_failures,
            profile_warning_reason_counts=profile_warning_reason_counts,
            awards_parse_failures=awards_parse_failures,
            awards_warning_reason_counts=awards_warning_reason_counts,
        )
        return self._silver_artifacts

    def build_current_gold_profiles(self, current_person_ids: set[int]) -> dict[int, BbrGoldProfile]:
        return project_current_gold_profiles(
            current_person_ids,
            self._load_accepted_bridge_rows(),
            self._load_profile_rows(),
        )
