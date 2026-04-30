from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from apps.assistant.semantic.llm_transport import (
    LlmTransportError,
    _gemini_model_candidates,
    call_gemini,
)


class _FakeResponse:
    def __init__(self, body: dict[str, object]) -> None:
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _http_error(code: int, body: str = '{"error":"temporary"}') -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.invalid",
        code=code,
        msg="error",
        hdrs={},
        fp=io.BytesIO(body.encode("utf-8")),
    )


class LlmTransportTests(unittest.TestCase):
    def test_default_gemini_fallback_is_gemini_3_flash_preview(self) -> None:
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-3.1-flash-lite-preview"}, clear=True):
            self.assertEqual(
                _gemini_model_candidates(),
                ["gemini-3.1-flash-lite-preview", "gemini-3-flash-preview"],
            )

    @patch("apps.assistant.semantic.llm_transport.time.sleep")
    @patch("apps.assistant.semantic.llm_transport.urllib.request.urlopen")
    def test_transient_primary_failure_uses_fallback_model(
        self,
        mock_urlopen,
        _mock_sleep,
    ) -> None:
        mock_urlopen.side_effect = [
            _http_error(503, '{"error":{"message":"high demand"}}'),
            _FakeResponse(
                {"candidates": [{"content": {"parts": [{"text": '{"status":"ok"}'}]}}]}
            ),
        ]

        with patch.dict(
            os.environ,
            {
                "LLM_INTERPRETER_PROVIDER": "google",
                "GEMINI_API_KEY": "test-key",
                "GEMINI_MODEL": "gemini-3.1-flash-lite-preview",
                "GEMINI_FALLBACK_MODELS": "gemini-3-flash-preview",
                "LLM_INTERPRETER_ATTEMPTS_PER_MODEL": "1",
            },
            clear=True,
        ):
            text = call_gemini("prompt")

        self.assertEqual(text, '{"status":"ok"}')
        urls = [call.args[0].full_url for call in mock_urlopen.call_args_list]
        self.assertIn("models/gemini-3.1-flash-lite-preview:generateContent", urls[0])
        self.assertIn("models/gemini-3-flash-preview:generateContent", urls[1])

    @patch("apps.assistant.semantic.llm_transport.urllib.request.urlopen")
    def test_non_transient_http_error_does_not_fallback(self, mock_urlopen) -> None:
        mock_urlopen.side_effect = _http_error(400, '{"error":{"message":"bad request"}}')

        with patch.dict(
            os.environ,
            {
                "LLM_INTERPRETER_PROVIDER": "google",
                "GEMINI_API_KEY": "test-key",
                "GEMINI_MODEL": "gemini-3.1-flash-lite-preview",
                "GEMINI_FALLBACK_MODELS": "gemini-3-flash-preview",
                "LLM_INTERPRETER_ATTEMPTS_PER_MODEL": "1",
            },
            clear=True,
        ):
            with self.assertRaises(LlmTransportError):
                call_gemini("prompt")

        self.assertEqual(mock_urlopen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
