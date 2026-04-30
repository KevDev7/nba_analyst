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
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    temperature = float(os.getenv("LLM_INTERPRETER_TEMPERATURE", "0"))
    if not api_key:
        raise LlmTransportError("Missing GEMINI_API_KEY for semantic interpretation.")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    body = ""
    for attempt in range(4):
        try:
            # Retry temporary provider failures, but surface persistent errors.
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 503} and attempt < 3:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise LlmTransportError(
                f"Gemini interpreter request failed with HTTP {exc.code}: {body[:500]}"
            ) from exc
        except Exception as exc:  # pragma: no cover - network exceptions are environment-specific
            raise LlmTransportError(f"Gemini interpreter request failed: {exc}") from exc

    try:
        payload_json = json.loads(body)
        return payload_json["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as exc:
        raise LlmTransportError("Gemini response did not contain a text candidate.") from exc
