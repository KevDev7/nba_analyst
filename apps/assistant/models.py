# Purpose:
# Define assistant-facing result models shared by pipeline and orchestrator.
#
# Uses:
# - CLI and web adapters
# - orchestrator/tool wrappers
#
# Produces:
# - stable product-facing assistant result shape

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AssistantResult:
    # The product-facing result of one assistant run.
    # Plain English: answer is what the user sees; debug is optional developer context.
    answer: str
    artifacts: list[dict[str, Any]] | None = None
    debug: dict[str, Any] | None = None
