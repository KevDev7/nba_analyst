# Purpose:
# Hold intermediate runtime artifacts outside the model context window.
#
# Uses:
# - results produced by query execution
#
# Produces:
# - a minimal runtime state object for the live slices
#
# Next:
# - analysis.py or AnswerSynthesis/package_results.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class RuntimeState:
    latest_result: Any | None = None
    artifacts: Dict[str, Any] = field(default_factory=dict)
