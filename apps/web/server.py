# Purpose:
# Serve the localhost NBA analyst web assistant.
#
# Uses:
# - the shared assistant pipeline from apps/assistant
# - a tiny static HTML/JS frontend
#
# Produces:
# - a browser page and POST /api/chat endpoint
#
# Next:
# - static/index.html

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.assistant import pipeline as assistant_pipeline
from apps.web.models import ChatRequest, ChatResponse


STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="NBA Analyst Web")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    # Serve the single local page. The page itself calls POST /api/chat.
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    # The only web-owned validation is "did the user submit anything?"
    # Semantic validity still belongs to the existing assistant pipeline.
    question = request.question.strip()
    if not question:
        return ChatResponse(ok=False, error="Question is required.")

    try:
        result = assistant_pipeline.run_assistant(question, debug=request.debug)
    except Exception as exc:
        return ChatResponse(ok=False, error=str(exc))

    return ChatResponse(
        ok=True,
        answer=result.answer,
        artifacts=result.artifacts or [],
        debug=result.debug,
    )
