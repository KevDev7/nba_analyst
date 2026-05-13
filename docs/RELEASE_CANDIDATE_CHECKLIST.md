# Release Candidate Checklist

## Production-Ready Architecture

- Haskell remains the only SQL author.
- `pipeline.py` remains the public compatibility wrapper.
- Governed tools are available for semantic query, catalog inspection, Python
  analysis, chart generation, artifact rendering, and answer composition.
- Per-run workspace resources can track approved tables, artifacts, findings,
  and provenance links between tool calls.
- The model tool loop resolves full tables server-side from workspace handles
  and finalizes answers through evidence validation.
- Data tables are separated from presentation artifacts.
- Vega-Lite chart artifacts are generated through `chart_generation.run` or the
  deterministic artifact renderer path, not arbitrary plotting code.
- Runtime SQL execution records safe metadata.
- Trace summaries and eval gates are available.
- Production config and rollback docs are present.

## Gated Beta Features

- `NBA_ENABLE_MODEL_ORCHESTRATOR`
- `NBA_MODEL_ORCHESTRATOR_DRY_RUN`
- `NBA_ENABLE_MODEL_TOOL_LOOP`
- `NBA_ENABLE_MODEL_ANSWER_COMPOSER`
- `NBA_ENABLE_MODEL_CHART_GENERATION`
- `NBA_ENABLE_SANDBOX_CHART_GENERATION`
- `NBA_ENABLE_PYTHON_CODE_SANDBOX`
- `NBA_PYTHON_CODE_SANDBOX_BACKEND=e2b_cloud`

## Verification Commands

Deterministic architecture suite:

```bash
python3 -m unittest \
  tests.test_model_orchestration_plans \
  tests.test_model_orchestration_evals \
  tests.test_model_orchestrator_gate \
  tests.test_model_tool_loop \
  tests.test_tool_registry \
  tests.test_run_workspace \
  tests.test_chart_generation_tool \
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

Compile check:

```bash
python3 -m compileall apps/assistant services/runtime-py/runtime tests
```

Architecture gates:

```bash
python3 scripts/run_architecture_gates.py
```

Broad suite:

```bash
python3 -m unittest discover tests
```

Live E2B smoke, optional:

```bash
NBA_ENABLE_PYTHON_CODE_SANDBOX=1 \
NBA_PYTHON_CODE_SANDBOX_BACKEND=e2b_cloud \
NBA_RUN_LIVE_E2B_TESTS=1 \
E2B_API_KEY=... \
python3 -m unittest tests.test_e2b_sandbox_live
```

## PR Summary

This branch migrates the assistant to a bounded orchestrator with governed
tools while preserving the ontology/Haskell retrieval boundary. It adds
production-ready contracts, provenance, eval gates, config, rollback docs, and
an E2B-backed sandbox path that remains disabled by default.

Known live-provider note: broad-suite tests that call Gemini may fail with
provider timeouts, high-demand 503s, or malformed JSON. Retry exact failures;
if they pass on retry and the error was provider transport/format flakiness,
record separately from deterministic architecture regressions.
