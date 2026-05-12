# Trace And Provenance

Slice 1 introduces a small assistant trace schema around the current deterministic path.

## Goals

- Record tool calls without changing product behavior.
- Keep SQL provenance without exposing raw SQL in model-visible/public payloads.
- Make future multi-tool orchestration observable.
- Preserve private debug as an explicitly gated channel.

## Schema

Current schema version:

```text
assistant_trace.v1
```

Shape:

```json
{
  "schema_version": "assistant_trace.v1",
  "run_id": "run_...",
  "created_at": "2026-05-12T00:00:00Z",
  "question": "Show me top players by points",
  "route": "deterministic_fast_path",
  "status": "ok",
  "assumptions": [],
  "tool_calls": [
    {
      "tool_call_id": "tc_...",
      "tool_name": "semantic_query.plan_execute",
      "status": "ok",
      "input": {
        "question": "Show me top players by points",
        "semantic_draft_hash": null,
        "mode": "plan_and_execute",
        "row_limit": 500,
        "caller": "orchestrator"
      },
      "output": {
        "query_id": "sq_...",
        "result_shape": "ranking",
        "row_count": 10,
        "artifact_count": 3,
        "row_limit_requested": 500,
        "row_limit_enforced": false
      },
      "provenance": {
        "ontology_path": "fixtures/ontology/semantic-gold.yaml",
        "snapshot_path": "fixtures/duckdb/gold_slice.duckdb",
        "planner": "ontology-hs",
        "planner_mode": "plan-semantic-draft-json",
        "execution_steps": [
          {
            "step_id": "sq_....step_1",
            "kind": "run_sql",
            "sql_hash": "sha256:...",
            "sql_redacted": true,
            "row_count": 10,
            "execution_ms": 83
          }
        ],
        "row_limit_requested": 500,
        "row_limit_enforced": false
      }
    }
  ],
  "artifacts": [
    {
      "artifact_id": "art_0",
      "kind": "text",
      "source_tool_call_id": "tc_..."
    }
  ],
  "claims": [],
  "errors": [],
  "private_debug": null
}
```

## SQL Policy

Raw SQL may exist inside:

- Haskell planner output.
- Python runtime execution internals.
- explicitly gated private debug.

Raw SQL must not be included in:

- model-visible orchestrator context.
- public API responses.
- artifact metadata.
- normal trace records.

Normal trace records use `sql_hash` and `sql_redacted: true`.

Private execution-plan debug is only available when all of these are true:

- `include_debug` is true;
- `include_private_sql` is true;
- `NBA_ALLOW_PRIVATE_SQL_TRACE` is enabled;
- the caller is trusted, such as `developer_test` or `local_cli`.

## Catalog And Artifact Provenance

`ontology_catalog.inspect` returns:

- `ontology_version` as a hash of `fixtures/ontology/semantic-gold.yaml`;
- `data_snapshot_id` as a hash of `fixtures/duckdb/gold_slice.duckdb`;
- coverage metadata read from DuckDB through a read-only connection.

`artifact_renderer.render` returns provenance for the artifact builder and chart bridge used to produce the artifact list. The artifact JSON shape remains the same public contract consumed by the CLI/web surfaces.

`python_analysis.run` returns:

- the controlled operation kind;
- the runtime name;
- parent table ids;
- output tables/artifacts/findings;
- parent table ids and output table ids;
- evidence references for generated findings where available.

It does not receive raw SQL, a DuckDB connection, network access, or arbitrary code in the current contract.

## Multi-Call Routes

The first governed multi-call route records two `semantic_query.plan_execute` trace entries, one `python_analysis.run` entry, and one `artifact_renderer.render` entry when debug output is requested. The route is currently deterministic and acceptance-test scoped; later model tool-calling should reuse the same trace shape instead of creating a separate observability format.
