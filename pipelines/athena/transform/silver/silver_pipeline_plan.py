from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SilverScriptSpec:
    script_name: str
    domain: str
    is_heavy: bool = False
    is_reconciliation: bool = False


SILVER_SCRIPT_PLAN = [
    SilverScriptSpec("build_silver_players.py", "identity"),
    SilverScriptSpec("build_silver_team_histories.py", "identity"),
    SilverScriptSpec("build_silver_player_movement.py", "player_movement"),
    SilverScriptSpec("build_silver_schedule.py", "schedule"),
    SilverScriptSpec("build_silver_boxscore_game.py", "boxscore"),
    SilverScriptSpec("build_silver_boxscore_player_game.py", "boxscore"),
    SilverScriptSpec("build_silver_boxscore_team_game.py", "boxscore"),
    SilverScriptSpec("build_silver_boxscore_matchups.py", "boxscore"),
    SilverScriptSpec("build_silver_boxscore_game_official.py", "boxscore"),
    SilverScriptSpec("build_silver_boxscore_team_period.py", "boxscore"),
    SilverScriptSpec("build_silver_playbyplay_events.py", "playbyplay", is_heavy=True),
    SilverScriptSpec("build_silver_shot_location_events.py", "shot_location", is_heavy=True),
    SilverScriptSpec("build_silver_pbpstats_event_projection_v1.py", "playbyplay", is_heavy=True),
    SilverScriptSpec("build_silver_event_projection_v2.py", "playbyplay", is_heavy=True),
    SilverScriptSpec("build_silver_pbpstats_event_context_v1.py", "playbyplay", is_heavy=True),
    SilverScriptSpec("build_silver_on_court_state.py", "on_court", is_heavy=True),
    SilverScriptSpec("build_silver_on_court_period_starter_qa.py", "on_court", is_heavy=True),
    SilverScriptSpec("build_silver_possessions.py", "possessions", is_heavy=True),
    SilverScriptSpec("build_silver_possessions_ot_fallback.py", "possessions", is_heavy=True),
    SilverScriptSpec("build_silver_player_game_possession_context.py", "game_context", is_heavy=True),
    SilverScriptSpec("build_silver_player_game_defensive_shot_context.py", "game_context", is_heavy=True),
    SilverScriptSpec("build_silver_player_game_opportunity_context.py", "game_context", is_heavy=True),
    SilverScriptSpec("build_silver_team_game_possession_context.py", "game_context", is_heavy=True),
    SilverScriptSpec("build_silver_team_game_defensive_shot_context.py", "game_context", is_heavy=True),
    SilverScriptSpec("validate_silver_reconciliation.py", "quality", is_reconciliation=True),
]


def select_silver_scripts(
    *,
    base_dir: Path,
    include_heavy: bool,
    skip_reconciliation: bool,
    only: set[str],
) -> list[Path]:
    selected_specs: list[SilverScriptSpec] = []
    for spec in SILVER_SCRIPT_PLAN:
        if spec.is_heavy and not include_heavy:
            continue
        if spec.is_reconciliation and skip_reconciliation:
            continue
        if only and spec.script_name not in only:
            continue
        selected_specs.append(spec)
    return [base_dir / spec.script_name for spec in selected_specs]


def known_silver_script_names() -> set[str]:
    return {spec.script_name for spec in SILVER_SCRIPT_PLAN}


def silver_domains() -> dict[str, list[str]]:
    domains: dict[str, list[str]] = {}
    for spec in SILVER_SCRIPT_PLAN:
        domains.setdefault(spec.domain, []).append(spec.script_name)
    return domains
