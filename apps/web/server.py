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

from fastapi import FastAPI

from apps.assistant import pipeline as assistant_pipeline
from apps.web.models import ChatRequest, ChatResponse


app = FastAPI(title="NBA Analyst API")


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
