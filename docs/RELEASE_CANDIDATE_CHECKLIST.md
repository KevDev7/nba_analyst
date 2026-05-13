# Release Candidate Checklist

## Production-Ready Architecture

- Haskell remains the only SQL author.
- `pipeline.py` remains the public compatibility wrapper.
- Governed tools are available for semantic query, catalog inspection, Python
  analysis, and artifact rendering.
- Data tables are separated from presentation artifacts.
- Runtime SQL execution records safe metadata.
- Trace summaries and eval gates are available.
- Production config and rollback docs are present.

## Gated Beta Features

- `NBA_ENABLE_MODEL_ORCHESTRATOR`
- `NBA_MODEL_ORCHESTRATOR_DRY_RUN`
- `NBA_ENABLE_MODEL_TOOL_LOOP`
- `NBA_ENABLE_MODEL_ANSWER_COMPOSER`
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
