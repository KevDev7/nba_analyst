# Production Config And Rollback

## Default Production Posture

Keep experimental capability gates off by default:

```text
NBA_ENABLE_MODEL_ORCHESTRATOR=0
NBA_MODEL_ORCHESTRATOR_DRY_RUN=0
NBA_ENABLE_MODEL_TOOL_LOOP=0
NBA_ENABLE_MODEL_ANSWER_COMPOSER=0
NBA_ENABLE_MODEL_CHART_GENERATION=0
NBA_ENABLE_SANDBOX_CHART_GENERATION=0
NBA_ENABLE_PYTHON_CODE_SANDBOX=0
NBA_PYTHON_CODE_SANDBOX_BACKEND=local_beta
NBA_RUN_LIVE_E2B_TESTS=0
NBA_ENABLE_PUBLIC_DEBUG=0
```

Required secrets:

```text
GEMINI_API_KEY=...
E2B_API_KEY=...  # only when enabling e2b_cloud code mode
```

## Sandbox Flags

```text
NBA_ENABLE_PYTHON_CODE_SANDBOX=1
NBA_PYTHON_CODE_SANDBOX_BACKEND=e2b_cloud
E2B_API_KEY=...
```

Code mode remains inside `python_analysis.run`. Controlled operations should be
preferred whenever they can express the analysis.

## Chart Generation Flags

```text
NBA_ENABLE_MODEL_CHART_GENERATION=1
NBA_ENABLE_SANDBOX_CHART_GENERATION=1
```

Deterministic `chart_generation.run` may be used as a governed chart tool.
Model/sandbox chart-spec generation stays off until chart eval gates pass.

## Live Test Flags

```text
NBA_RUN_LIVE_E2B_TESTS=1
```

Live E2B tests also require `E2B_API_KEY`.

## Rollback

1. Set `NBA_ENABLE_MODEL_ORCHESTRATOR=0`.
2. Set `NBA_ENABLE_MODEL_TOOL_LOOP=0`.
3. Set `NBA_ENABLE_MODEL_ANSWER_COMPOSER=0`.
4. Set `NBA_ENABLE_MODEL_CHART_GENERATION=0`.
5. Set `NBA_ENABLE_SANDBOX_CHART_GENERATION=0`.
6. Set `NBA_ENABLE_PYTHON_CODE_SANDBOX=0`.
7. Keep `NBA_ENABLE_PUBLIC_DEBUG=0`.
8. Redeploy the backend.

This returns the product to deterministic fast path plus deterministic governed
routes and controlled local analysis operations.

## Budget And Concurrency Caution

Do not enable E2B code mode publicly until the owning account, budget,
concurrency cap, retention policy, and incident rollback owner are explicit.
