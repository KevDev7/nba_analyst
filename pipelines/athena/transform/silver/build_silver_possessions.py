"""Stable entrypoint for the silver possessions transform."""

from __future__ import annotations

import sys

from possessions import build as _impl


if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl

