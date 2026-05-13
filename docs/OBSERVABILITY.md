# Observability

The assistant records rich traces for debugging, but production logs should use
safe summaries rather than full debug payloads.

Use `apps.assistant.trace.safe_trace_summary(...)` to derive a production-safe
record.

## Safe Summary Fields

- `run_id`
- `route`
- `status`
- `tool_names`
- `tool_count`
- `artifact_count`
- `claim_count`
- `error_codes`
- `sql_steps` with `sql_hash`, row counts, row-limit/truncation status, and
  execution duration
- `tool_durations`
- `sandbox_backends`
- `sandbox_rejections`
- `has_private_debug`

## Redaction Rules

Safe summaries must not include:

- raw SQL;
- raw execution plans;
- private debug payloads;
- credentials;
- raw user/model code;
- huge table rows;
- database handles or filesystem paths.

## Useful Production Counters

- route distribution;
- model-planner fallback rate;
- model-composer validation/fallback rate;
- sandbox backend usage;
- sandbox rejection reason counts;
- SQL execution duration and truncation rates;
- tool duration percentiles;
- unsupported-surface refusal counts.
