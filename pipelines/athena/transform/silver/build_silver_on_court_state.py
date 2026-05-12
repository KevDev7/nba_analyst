"""Stable entrypoint for the silver on-court state transform."""

from __future__ import annotations

import sys

from on_court import state as _impl


if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl

