"""Stable entrypoint for the silver player-game possession context transform."""

from __future__ import annotations

import sys

try:
    from .game_context import player_possession as _impl
except ImportError:  # Direct script execution from the silver transform directory.
    from game_context import player_possession as _impl


if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
