from __future__ import annotations

from dataclasses import dataclass

from .bbr_projection import build_bbr_by_person_id
from .current_profile import (
    build_current_person_ids,
    build_current_profile_map,
    build_extended_rows,
)
from .history import build_dim_player_rows
from .sources import GoldPlayerSurfaceSources


@dataclass(frozen=True)
class GoldPlayerSurfaceArtifacts:
    dim_player_rows: list[dict]
    extended_player_dim_rows: list[dict]


class GoldPlayerSurfacePipeline:
    def build_player_surface(self, sources: GoldPlayerSurfaceSources) -> GoldPlayerSurfaceArtifacts:
        dim_player_rows, _ = build_dim_player_rows(
            sources.player_table,
            sources.game_table,
            sources.player_bio_table,
            sources.dim_team_table,
            sources.bbr_bridge_table,
            sources.bbr_profile_table,
        )
        current_person_ids = build_current_person_ids(sources.dim_player_table)
        current_profile_by_person = build_current_profile_map(
            sources.player_table,
            sources.game_table,
            sources.player_bio_table,
            sources.dim_team_table,
        )
        bbr_by_person_id = build_bbr_by_person_id(
            sources.bbr_bridge_table,
            sources.bbr_profile_table,
        )
        return GoldPlayerSurfaceArtifacts(
            dim_player_rows=dim_player_rows,
            extended_player_dim_rows=build_extended_rows(
                current_person_ids,
                current_profile_by_person,
                bbr_by_person_id,
            ),
        )
