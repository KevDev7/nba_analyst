from __future__ import annotations

import sys
from pathlib import Path


SILVER_TRANSFORM_DIR = (
    Path(__file__).resolve().parents[2] / "transform" / "silver"
)
if str(SILVER_TRANSFORM_DIR) not in sys.path:
    sys.path.insert(0, str(SILVER_TRANSFORM_DIR))

from silver_pipeline_plan import (  # noqa: E402
    known_silver_script_names,
    select_silver_scripts,
    silver_domains,
)


def test_select_silver_scripts_excludes_heavy_by_default():
    scripts = select_silver_scripts(
        base_dir=SILVER_TRANSFORM_DIR,
        include_heavy=False,
        skip_reconciliation=False,
        only=set(),
    )
    script_names = [path.name for path in scripts]

    assert "build_silver_boxscore_game.py" in script_names
    assert "build_silver_playbyplay_events.py" not in script_names
    assert script_names[-1] == "validate_silver_reconciliation.py"


def test_select_silver_scripts_can_include_heavy_and_skip_reconciliation():
    scripts = select_silver_scripts(
        base_dir=SILVER_TRANSFORM_DIR,
        include_heavy=True,
        skip_reconciliation=True,
        only=set(),
    )
    script_names = [path.name for path in scripts]

    assert "build_silver_playbyplay_events.py" in script_names
    assert "build_silver_team_game_defensive_shot_context.py" in script_names
    assert "validate_silver_reconciliation.py" not in script_names


def test_select_silver_scripts_only_filters_against_plan_order():
    scripts = select_silver_scripts(
        base_dir=SILVER_TRANSFORM_DIR,
        include_heavy=True,
        skip_reconciliation=False,
        only={
            "build_silver_boxscore_team_game.py",
            "build_silver_boxscore_game.py",
        },
    )

    assert [path.name for path in scripts] == [
        "build_silver_boxscore_game.py",
        "build_silver_boxscore_team_game.py",
    ]


def test_known_silver_script_names_and_domains_are_navigable():
    names = known_silver_script_names()
    domains = silver_domains()

    assert "build_silver_boxscore_matchups.py" in names
    assert "build_silver_shot_location_events.py" in domains["shot_location"]
    assert "build_silver_schedule.py" in domains["schedule"]
