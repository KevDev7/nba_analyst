# Purpose:
# Define the local web API request and response shapes.
#
# Uses:
# - browser requests from the simple HTML/JS page
# - FastAPI response validation
#
# Produces:
# - stable JSON payloads for one-question assistant calls
#
# Next:
# - server.py

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    # One browser-submitted analytics question.
    # Plain English: this mirrors the CLI's one terminal command.
    question: str = Field(default="")
    debug: bool = False


class ChatResponse(BaseModel):
    # The web-facing result shape.
    # Plain English: every request returns either one answer or one clear error.
    ok: bool
    answer: Optional[str] = None
    error: Optional[str] = None
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    debug: Optional[Dict[str, Any]] = None
