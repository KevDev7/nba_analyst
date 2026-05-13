# Testing

## Deterministic Architecture Suite

Use this suite for normal development and CI. It does not require Gemini or E2B
credentials.

```bash
python3 -m unittest \
  tests.test_model_orchestration_plans \
  tests.test_model_orchestration_evals \
  tests.test_model_orchestrator_gate \
  tests.test_model_tool_loop \
  tests.test_trace_eval_harness \
  tests.test_trace_observability \
  tests.test_orchestrator_evals \
  tests.test_python_code_sandbox \
  tests.test_python_code_sandbox_evals \
  tests.test_e2b_sandbox_live \
  tests.test_python_analysis_tool \
  tests.test_local_analysis_worker \
  tests.test_analysis_tool_contract \
  tests.test_sql_governance
```

`tests.test_e2b_sandbox_live` is included here because it skips unless live E2B
flags are present.

## Live Gemini Smoke Tests

Some legacy assistant tests call Gemini for semantic interpretation. They can
fail with provider timeouts, high-demand 503s, or malformed JSON. For release
checks, run the broad suite and retry exact live-provider failures once.

```bash
python3 -m unittest discover tests
```

If a failing test passes on exact retry and the error was a provider timeout,
503, or malformed JSON response, record it as provider flakiness rather than a
code regression.

## Live E2B Smoke Test

Live E2B execution is optional and must be explicitly enabled:

```bash
NBA_ENABLE_PYTHON_CODE_SANDBOX=1 \
NBA_PYTHON_CODE_SANDBOX_BACKEND=e2b_cloud \
NBA_RUN_LIVE_E2B_TESTS=1 \
E2B_API_KEY=... \
python3 -m unittest tests.test_e2b_sandbox_live
```

Normal tests use `mock_e2b` or skipped live tests and must not require E2B
credentials.
