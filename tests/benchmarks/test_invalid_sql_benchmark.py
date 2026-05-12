from __future__ import annotations

import json
import os
import re
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import duckdb
from dotenv import load_dotenv

from apps.assistant.pipeline import run_assistant
from apps.assistant.semantic.interpreter import interpret_question_to_semantic_draft


ROOT = Path(__file__).resolve().parents[2]
QUESTION_BANK_PATH = ROOT / "evals" / "question_bank.json"
DUCKDB_PATH = ROOT / "fixtures" / "duckdb" / "gold_slice.duckdb"
RUN_ENV = "NBA_RUN_LIVE_LLM_BENCHMARKS"


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _supported_questions() -> list[str]:
    payload = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
    return [case["question"] for case in payload["cases"] if case.get("status") == "supported"]


def _schema_text(conn: duckdb.DuckDBPyConnection) -> str:
    lines: list[str] = []
    for (table_name,) in conn.execute("SHOW TABLES").fetchall():
        if table_name == "snapshot_meta":
            continue
        columns = [row[0] for row in conn.execute(f"DESCRIBE {table_name}").fetchall()]
        lines.append(f"{table_name}({', '.join(columns)})")
    return "\n".join(lines)


def _extract_sql(raw_text: str) -> str:
    try:
        payload = json.loads(raw_text)
        return str(payload.get("sql", "")).strip().rstrip(";")
    except json.JSONDecodeError:
        fenced = re.search(r"```(?:sql)?\s*(.*?)```", raw_text, flags=re.IGNORECASE | re.DOTALL)
        return (fenced.group(1) if fenced else raw_text).strip().rstrip(";")


def _call_direct_sql_gemini(question: str, schema: str) -> str:
    load_dotenv(ROOT / ".env", override=False)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise unittest.SkipTest("GEMINI_API_KEY is required for the live LLM SQL benchmark.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    prompt = f"""
You are generating DuckDB SQL for an NBA analytics database.
Return JSON only: {{"sql":"..."}}.
Rules:
- Generate a single read-only SELECT query.
- Use only the tables and columns in this schema.
- Do not use markdown fences.
- If a name is partial, use ILIKE on name columns.
- Use LIMIT when the user asks for top N or rows.
Schema:
{schema}
Question: {question}
""".strip()
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
            raw_text = body["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_sql(raw_text)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {429, 500, 502, 503, 504} and attempt == 0:
                time.sleep(1.5)
                continue
            raise
    raise RuntimeError(f"Direct SQL benchmark failed: {last_error}")


@unittest.skipUnless(_enabled(RUN_ENV), f"Set {RUN_ENV}=1 to run live LLM benchmarks.")
class InvalidSqlBenchmarkTests(unittest.TestCase):
    def test_semantic_planner_reduces_sql_execution_failures_vs_direct_llm_sql(self) -> None:
        questions = _supported_questions()
        direct_invalid = 0
        direct_valid = 0
        semantic_invalid = 0
        semantic_valid = 0
        direct_failures: list[dict[str, str]] = []
        semantic_failures: list[dict[str, str]] = []

        interpret_question_to_semantic_draft.cache_clear()
        with duckdb.connect(str(DUCKDB_PATH), read_only=True) as conn:
            schema = _schema_text(conn)
            for question in questions:
                try:
                    sql = _call_direct_sql_gemini(question, schema)
                    if not sql.lower().lstrip().startswith("select"):
                        raise RuntimeError("Generated SQL was empty or not a SELECT.")
                    conn.execute(f"SELECT * FROM ({sql}) AS direct_sql_probe LIMIT 5").fetchall()
                    direct_valid += 1
                except Exception as exc:
                    direct_invalid += 1
                    direct_failures.append(
                        {"question": question, "error": str(exc).splitlines()[0][:220]}
                    )

        for question in questions:
            try:
                result = run_assistant(question, debug=False)
                if not result.answer.strip():
                    raise RuntimeError("Semantic path returned an empty answer.")
                semantic_valid += 1
            except Exception as exc:
                semantic_invalid += 1
                semantic_failures.append(
                    {"question": question, "error": str(exc).splitlines()[0][:220]}
                )

        invalid_reduction_pct = (
            0.0
            if direct_invalid == 0
            else (direct_invalid - semantic_invalid) / direct_invalid * 100
        )
        result = {
            "questions": len(questions),
            "direct_llm_sql_valid": direct_valid,
            "direct_llm_sql_invalid": direct_invalid,
            "semantic_path_valid": semantic_valid,
            "semantic_path_invalid": semantic_invalid,
            "invalid_sql_reduction_pct": round(invalid_reduction_pct, 1),
            "direct_failures": direct_failures,
            "semantic_failures": semantic_failures,
        }
        print("INVALID_SQL_BENCHMARK_JSON", json.dumps(result, sort_keys=True))

        self.assertLess(semantic_invalid, direct_invalid)
