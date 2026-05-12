# Purpose:
# Serve the localhost NBA analyst assistant API.
#
# Uses:
# - the shared assistant pipeline from apps/assistant
#
# Produces:
# - POST /api/chat endpoint
#
# Next:
# - apps/web-ui for the structured frontend

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.assistant import pipeline as assistant_pipeline
from apps.web.models import ChatRequest, ChatResponse
from scripts import load_gold_snapshot


app = FastAPI(title="NBA Analyst API")
ALLOWED_ORIGINS_ENV = "NBA_ALLOWED_ORIGINS"
PUBLIC_DEBUG_ENV = "NBA_ENABLE_PUBLIC_DEBUG"
MAX_QUESTION_CHARS_ENV = "NBA_MAX_QUESTION_CHARS"


def _env_flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _public_debug_enabled() -> bool:
    return _env_flag_enabled(PUBLIC_DEBUG_ENV)


def _effective_debug_requested(request_debug: bool) -> bool:
    return request_debug and _public_debug_enabled()


def _max_question_chars() -> int | None:
    raw_limit = os.getenv(MAX_QUESTION_CHARS_ENV, "").strip()
    if not raw_limit:
        return None
    try:
        limit = int(raw_limit)
    except ValueError:
        return None
    if limit < 1:
        return None
    return limit


def _question_too_long_message(limit: int) -> str:
    return f"Question is too long. Please keep it under {limit} characters."


def _allowed_origins_from_env() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv(ALLOWED_ORIGINS_ENV, "").split(",")
        if origin.strip()
    ]


def _configure_cors(api: FastAPI) -> None:
    allowed_origins = _allowed_origins_from_env()
    if not allowed_origins:
        return
    api.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_configure_cors(app)


@app.get("/healthz")
def healthz():
    checks: list[str] = []
    planner_bin = os.getenv(assistant_pipeline.PLANNER_BINARY_ENV, "").strip()
    if planner_bin and not Path(planner_bin).is_file():
        checks.append("planner_binary_missing")
    if not load_gold_snapshot.DB_PATH.exists():
        checks.append("duckdb_snapshot_missing")
    elif not load_gold_snapshot._snapshot_is_current(load_gold_snapshot.DB_PATH):
        checks.append("duckdb_snapshot_stale")

    if checks:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ok": False, "status": "unready", "checks": checks},
        )
    return {"ok": True, "status": "ready", "checks": []}


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    # The only web-owned validation is "did the user submit anything?"
    # Semantic validity still belongs to the existing assistant pipeline.
    question = request.question.strip()
    if not question:
        return ChatResponse(ok=False, error="Question is required.")
    max_question_chars = _max_question_chars()
    if max_question_chars is not None and len(question) > max_question_chars:
        return ChatResponse(ok=False, error=_question_too_long_message(max_question_chars))

    try:
        result = assistant_pipeline.run_assistant(
            question,
            debug=_effective_debug_requested(request.debug),
        )
    except Exception as exc:
        return ChatResponse(ok=False, error=str(exc))

    return ChatResponse(
        ok=True,
        answer=result.answer,
        artifacts=result.artifacts or [],
        debug=result.debug,
    )
