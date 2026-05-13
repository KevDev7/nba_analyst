# Model Orchestration Beta Policy

The deterministic fast path remains the production default.

## States

### Off

Default. `NBA_ENABLE_MODEL_ORCHESTRATOR` is unset/false. Requests use
deterministic routing and `semantic_query.plan_execute`.

### Dry Run

`NBA_ENABLE_MODEL_ORCHESTRATOR=1` and `NBA_MODEL_ORCHESTRATOR_DRY_RUN=1`.

The model returns a validated structured plan and planned tool sequence, but no
tools are executed. Use this for eval collection and planner tuning.

### Structured Plan Beta

`NBA_ENABLE_MODEL_ORCHESTRATOR=1` and dry-run is off.

The model may produce a validated plan. Execution reuses governed tools only.
Planner or execution failure falls back to deterministic routing.

### Tool Loop Beta

`NBA_ENABLE_MODEL_ORCHESTRATOR=1` and `NBA_ENABLE_MODEL_TOOL_LOOP=1`.

The iterative loop can request only:

- `ontology_catalog.inspect`
- `semantic_query.plan_execute`
- `python_analysis.run`
- `artifact_renderer.render`

It remains beta and must not be the default route.

## Answer Composer

`NBA_ENABLE_MODEL_ANSWER_COMPOSER=1` enables model-assisted answer composition
from structured evidence only. Claims must pass evidence validation or the
assistant falls back to deterministic table-first output.

## Permanent Limits

- No model-authored SQL.
- No raw SQL or execution plans in model context.
- No direct `python_code` tool.
- No DuckDB/database access.
- No unsupported surfaces unless represented as a grounded limitation.
