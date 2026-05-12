"""Stable entrypoint for the silver pbpstats event context v1 transform."""

from __future__ import annotations

import sys

from pbpstats_events import context_v1 as _impl


if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
