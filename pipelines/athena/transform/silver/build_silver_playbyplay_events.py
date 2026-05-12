"""Stable entrypoint for the silver play-by-play events transform."""

from __future__ import annotations

from playbyplay.events import *  # noqa: F401,F403
from playbyplay.events import main


if __name__ == "__main__":
    main()

