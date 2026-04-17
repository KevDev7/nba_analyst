"""
Create Athena view for player-game source shot-type breakdowns.

Managed views:
  - vw_player_game_shot_type_source
"""

from __future__ import annotations

try:
    from pipelines.athena.transform.gold.athena_view_helpers import (
        AthenaClient,
        DIM_GAME_TABLE,
        DIM_PLAYER_TABLE,
        PLAYER_GAME_SHOT_TYPE_SOURCE_TABLE,
        load_settings,
    )
except ModuleNotFoundError:
    from athena_view_helpers import (  # type: ignore[no-redef]
        AthenaClient,
        DIM_GAME_TABLE,
        DIM_PLAYER_TABLE,
        PLAYER_GAME_SHOT_TYPE_SOURCE_TABLE,
        load_settings,
    )


VIEW_NAME = "vw_player_game_shot_type_source"


def build_view_sql(view_name: str = VIEW_NAME) -> str:
    return f"""-- Auto-generated from {PLAYER_GAME_SHOT_TYPE_SOURCE_TABLE}, {DIM_GAME_TABLE}, and {DIM_PLAYER_TABLE}.
-- Re-run deploy_player_game_shot_type_source_view.py after changing any selected source columns.
CREATE OR REPLACE VIEW "{view_name}" AS
WITH "current_player_dim" AS (
    SELECT
        "person_id",
        COALESCE("display_name", "player_name") AS "player_name"
    FROM "{DIM_PLAYER_TABLE}"
    WHERE COALESCE("is_current", 0) = 1
)
SELECT
    "pgst"."person_id" AS "player_id",
    COALESCE("cpd"."player_name", '') AS "player_name",
    "pgst"."game_id" AS "game_id",
    CAST("pgst"."game_date" AS VARCHAR) AS "game_date",
    "pgst"."season_year" AS "season_year",
    "pgst"."season_type" AS "season_type",
    "pgst"."team_id" AS "team_id",
    CASE
        WHEN "dg"."home_team_id" = "pgst"."team_id" THEN "dg"."home_team_abbreviation"
        ELSE "dg"."away_team_abbreviation"
    END AS "team",
    "pgst"."opponent_team_id" AS "opponent_team_id",
    CASE
        WHEN "dg"."home_team_id" = "pgst"."team_id" THEN "dg"."away_team_abbreviation"
        ELSE "dg"."home_team_abbreviation"
    END AS "opponent",
    CASE
        WHEN "dg"."home_team_id" = "pgst"."team_id" THEN 'Home'
        ELSE 'Away'
    END AS "home_away",
    "pgst"."source_shot_type_key" AS "shot_type_key",
    "pgst"."source_shot_type_label" AS "shot_type",
    "pgst"."source_shot_type_family" AS "shot_family",
    "pgst"."action_type" AS "action_type",
    "pgst"."sub_type" AS "sub_type",
    "pgst"."descriptor" AS "descriptor",
    "pgst"."shot_value" AS "shot_value",
    "pgst"."is_two_point_shot" AS "is_two_point_shot",
    "pgst"."is_three_point_shot" AS "is_three_point_shot",
    "pgst"."field_goals_attempted" AS "field_goals_attempted",
    "pgst"."field_goals_made" AS "field_goals_made",
    "pgst"."three_pointers_attempted" AS "three_pointers_attempted",
    "pgst"."three_pointers_made" AS "three_pointers_made",
    "pgst"."points_from_field_goals" AS "points_from_field_goals"
FROM "{PLAYER_GAME_SHOT_TYPE_SOURCE_TABLE}" AS "pgst"
INNER JOIN "{DIM_GAME_TABLE}" AS "dg"
    ON "pgst"."game_id" = "dg"."game_id"
LEFT JOIN "current_player_dim" AS "cpd"
    ON "pgst"."person_id" = "cpd"."person_id"
""".strip()


def deploy_player_game_shot_type_source_view() -> None:
    settings = load_settings()
    athena_client = AthenaClient(settings)
    athena_client.execute(build_view_sql())
    print(f"Created or replaced view: {settings.database}.{VIEW_NAME}")


if __name__ == "__main__":
    deploy_player_game_shot_type_source_view()
