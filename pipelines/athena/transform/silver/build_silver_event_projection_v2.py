"""Stable entrypoint for the silver raw-first event projection v2 transform."""

from __future__ import annotations

from event_projection.v2 import *  # noqa: F401,F403
from event_projection.v2 import main


if __name__ == "__main__":
    main()

