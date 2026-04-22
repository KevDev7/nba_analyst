"""Deploy the currently supported Athena gold views."""

from __future__ import annotations

try:
    from pipelines.athena.transform.silver.deploy_player_game_opportunity_context_table import (
        main as deploy_player_game_opportunity_context_table,
    )
    from pipelines.athena.transform.silver.deploy_player_game_defensive_shot_context_table import (
        main as deploy_player_game_defensive_shot_context_table,
    )
    from pipelines.athena.transform.silver.deploy_player_game_possession_context_table import (
        main as deploy_player_game_possession_context_table,
    )
    from pipelines.athena.transform.gold.deploy_player_season_provenance_debug_view import (
        deploy_player_season_provenance_debug_view,
    )
    from pipelines.athena.transform.gold.deploy_player_season_boxscore_advanced_view import (
        deploy_player_season_boxscore_advanced_view,
    )
    from pipelines.athena.transform.gold.deploy_player_game_shot_type_source_view import (
        deploy_player_game_shot_type_source_view,
    )
    from pipelines.athena.transform.gold.deploy_team_season_boxscore_advanced_view import (
        deploy_team_season_boxscore_advanced_view,
    )
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        DEFERRED_VIEW_NAMES,
        RETIRED_VIEW_NAMES,
        SUPPORTED_VIEW_NAMES,
        load_settings,
    )
except ModuleNotFoundError:
    from pipelines.athena.transform.silver.deploy_player_game_opportunity_context_table import (  # type: ignore[no-redef]
        main as deploy_player_game_opportunity_context_table,
    )
    from pipelines.athena.transform.silver.deploy_player_game_defensive_shot_context_table import (  # type: ignore[no-redef]
        main as deploy_player_game_defensive_shot_context_table,
    )
    from pipelines.athena.transform.silver.deploy_player_game_possession_context_table import (  # type: ignore[no-redef]
        main as deploy_player_game_possession_context_table,
    )
    from deploy_player_season_provenance_debug_view import deploy_player_season_provenance_debug_view  # type: ignore[no-redef]
    from deploy_player_season_boxscore_advanced_view import deploy_player_season_boxscore_advanced_view  # type: ignore[no-redef]
    from deploy_player_game_shot_type_source_view import deploy_player_game_shot_type_source_view  # type: ignore[no-redef]
    from deploy_team_season_boxscore_advanced_view import deploy_team_season_boxscore_advanced_view  # type: ignore[no-redef]
    from athena_view_helpers import (  # type: ignore[no-redef]
        AthenaClient,
        DEFERRED_VIEW_NAMES,
        RETIRED_VIEW_NAMES,
        SUPPORTED_VIEW_NAMES,
        load_settings,
    )


SUPPORTED_DEPLOYERS = [
    "deploy_player_season_boxscore_advanced_view",
    "deploy_player_game_shot_type_source_view",
    "deploy_team_season_boxscore_advanced_view",
]

INTERNAL_DEPLOYERS = [
    "deploy_player_season_provenance_debug_view",
]


def drop_non_supported_views() -> None:
    settings = load_settings()
    athena_client = AthenaClient(settings)
    for view_name in DEFERRED_VIEW_NAMES + RETIRED_VIEW_NAMES:
        athena_client.execute(f'DROP VIEW IF EXISTS "{view_name}"')
        print(f"Dropped non-supported view if present: {settings.database}.{view_name}")


def deploy_all_views() -> None:
    deploy_player_game_opportunity_context_table()
    deploy_player_game_possession_context_table()
    deploy_player_game_defensive_shot_context_table()
    deploy_player_season_provenance_debug_view()
    deploy_player_season_boxscore_advanced_view()
    deploy_player_game_shot_type_source_view()
    deploy_team_season_boxscore_advanced_view()
    drop_non_supported_views()


if __name__ == "__main__":
    deploy_all_views()
