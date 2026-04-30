# Purpose:
# Own the low-level LLM provider call used by the semantic interpreter.
#
# Uses:
# - root .env Gemini config
# - urllib HTTP transport
#
# Produces:
# - raw model text for interpreter.py to parse and validate

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_GEMINI_FALLBACK_MODELS = "gemini-3-flash-preview"
TRANSIENT_HTTP_CODES = {429, 500, 502, 503, 504}

# Find the project root and load API/model configuration from .env.
load_dotenv(ROOT / ".env", override=False)


class LlmTransportError(RuntimeError):
    """Raised when the LLM transport cannot return raw model text."""


def call_gemini(prompt: str) -> str:
    # Send the semantic-draft prompt to Gemini and return the model's text.
    provider = os.getenv("LLM_INTERPRETER_PROVIDER", "google")
    if provider != "google":
        raise LlmTransportError(
            f"Unsupported LLM_INTERPRETER_PROVIDER '{provider}'. This assistant supports 'google' only."
        )

    api_key = os.getenv("GEMINI_API_KEY")
    temperature = float(os.getenv("LLM_INTERPRETER_TEMPERATURE", "0"))
    attempts_per_model = max(1, int(os.getenv("LLM_INTERPRETER_ATTEMPTS_PER_MODEL", "1")))
    if not api_key:
        raise LlmTransportError("Missing GEMINI_API_KEY for semantic interpretation.")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }
    transient_errors: list[str] = []
    for model in _gemini_model_candidates():
        request = _build_gemini_request(api_key=api_key, model=model, payload=payload)
        for attempt in range(attempts_per_model):
            try:
                # Retry temporary provider failures, then try the next configured model.
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read().decode("utf-8")
                return _extract_gemini_text(body)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in TRANSIENT_HTTP_CODES:
                    transient_errors.append(f"{model}: HTTP {exc.code}: {body[:250]}")
                    if attempt < attempts_per_model - 1:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    break
                raise LlmTransportError(
                    f"Gemini interpreter request failed with HTTP {exc.code}: {body[:500]}"
                ) from exc
            except Exception as exc:  # pragma: no cover - network exceptions are environment-specific
                raise LlmTransportError(f"Gemini interpreter request failed: {exc}") from exc

    details = " | ".join(transient_errors[-4:])
    raise LlmTransportError(f"Gemini interpreter request failed for all configured models: {details}")


def _gemini_model_candidates() -> list[str]:
    # Keep fallback at the transport boundary so the semantic draft contract stays unchanged.
    primary = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip()
    raw_fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", DEFAULT_GEMINI_FALLBACK_MODELS)
    candidates = [primary]
    candidates.extend(model.strip() for model in raw_fallbacks.split(",") if model.strip())
    deduped: list[str] = []
    for model in candidates:
        if model not in deduped:
            deduped.append(model)
    return deduped


def _build_gemini_request(
    *,
    api_key: str,
    model: str,
    payload: dict[str, object],
) -> urllib.request.Request:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    return urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def _extract_gemini_text(body: str) -> str:
    try:
        payload_json = json.loads(body)
        return payload_json["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:
        raise LlmTransportError("Gemini response did not contain a text candidate.") from exc
