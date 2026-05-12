# Tool Contracts

This document defines the assistant tool contracts used by the orchestrator layer.

## Current Tools

### `semantic_query.plan_execute`

Purpose: wrap the current ontology-grounded assistant path as one governed tool call.

Current behavior:

```text
semantic_query.plan_execute
  -> semantic draft interpretation
  -> Python assumptions/entity resolution
  -> Haskell ontology planning
  -> Python runtime execution
  -> answer synthesis
  -> text/table/chart artifacts
```

This tool is not a raw SQL tool. Haskell remains the SQL author.

Input shape:

```json
{
  "request_id": "optional string",
  "question": "string or null",
  "semantic_draft": "object or null",
  "mode": "plan_and_execute",
  "row_limit": 500,
  "include_debug": false,
  "include_private_sql": false,
  "caller": "orchestrator"
}
```

Validation:

- Exactly one of `question` or `semantic_draft` is required.
- `mode` is currently only `plan_and_execute`.
- `row_limit` is a contract field for future governance; Slice 1 does not yet enforce SQL-level caps.
- `include_private_sql` must remain false for model-visible or public contexts.

Output shape:

```json
{
  "ok": true,
  "query_id": "sq_...",
  "status": "answered",
  "result_shape": "ranking",
  "answer_text": "...",
  "artifacts": [],
  "tables": [],
  "answer_context": {},
  "assumptions": [],
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
        "row_count": 10
      }
    ]
  },
  "trace": {},
  "debug": null,
  "error": null
}
```

Failure shape:

```json
{
  "ok": false,
  "query_id": "sq_...",
  "status": "failed",
  "error": {
    "code": "semantic_query_failed",
    "message": "...",
    "stage": null
  }
}
```

### `ontology_catalog.inspect`

Purpose: expose ontology-backed subjects, metrics, dimensions, filters, time grains, and snapshot coverage before the orchestrator retrieves data.

Current implementation:

- reads `fixtures/ontology/semantic-gold.yaml`;
- reads coverage metadata from `fixtures/duckdb/gold_slice.duckdb`;
- returns ontology and snapshot hashes;
- does not replace Haskell ontology validation.

Input shape:

```json
{
  "facets": ["subjects", "metrics", "dimensions", "filters", "time_grains", "coverage"],
  "subject_hint": "teams",
  "search": "net rating",
  "include_aliases": true,
  "include_limitations": true,
  "max_items": 200
}
```

Output shape:

```json
{
  "ok": true,
  "ontology_version": "semantic-gold:<sha256>",
  "data_snapshot_id": "gold-snapshot:<sha256>",
  "coverage": {
    "seasons": ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"],
    "season_types": ["playoffs", "regular_season"],
    "default_season": "2025-26",
    "default_season_type": "regular_season",
    "lowest_grain": "game",
    "unsupported_surfaces": ["play_by_play", "lineups", "on_off", "clutch", "shot_location"]
  },
  "subjects": [],
  "metrics": [],
  "dimensions": [],
  "filters": [],
  "time_grains": [],
  "limitations": []
}
```

This is a read-only catalog tool. Its job is to make the schema contract inspectable by the orchestrator, not to infer new concepts that are absent from the ontology.

### `artifact_renderer.render`

Purpose: build renderer-friendly artifacts from grounded answer payloads through one tool boundary.

Current behavior:

```text
artifact_renderer.render
  -> build text/table artifacts from FinalAnswer
  -> optionally call the existing chart bridge
  -> return the same artifact JSON shape the web/CLI already consume
```

Input shape:

```json
{
  "question": "Show the ranking as a chart",
  "answer": "<FinalAnswer object>",
  "artifacts": null,
  "allowed_artifact_kinds": ["text", "table", "chart"]
}
```

Output shape:

```json
{
  "ok": true,
  "artifacts": [],
  "artifact_count": 3,
  "provenance": {
    "source": "runtime.AnswerSynthesis.artifacts",
    "chart_bridge": "apps.assistant.chart_artifacts.append_chart_artifacts"
  },
  "error": null
}
```

This wrapper is intentionally thin in Slice 2. It creates the tool boundary while preserving the current UI artifact contract.

### `python_analysis.run`

Purpose: run controlled derived analysis over approved input tables. This is not arbitrary Python execution and does not receive a database handle.

Current controlled operations:

- `join_and_delta`: joins two tables on declared keys and computes `right_metric - left_metric`.
- `rank_extremes`: sorts one table by a numeric metric and adds a deterministic rank column.
- chart operations remain available through the same runtime contract for artifact generation.

Input shape:

```json
{
  "request_id": "analysis_...",
  "analysis_request": {
    "tool": "python_analysis",
    "runtime": "local_trusted",
    "tables": [
      {
        "id": "q_2023_24.primary",
        "title": "2023-24 team average points",
        "columns": [
          {"id": "team", "label": "Team", "type": "text"},
          {"id": "avg_points", "label": "2023-24 Avg Points", "type": "number"}
        ],
        "rows": []
      }
    ],
    "operation": {
      "kind": "join_and_delta",
      "left_table_id": "q_2023_24.primary",
      "right_table_id": "q_2024_25.primary",
      "join_keys": ["team"],
      "left_metric": "avg_points",
      "right_metric": "avg_points",
      "left_output_column": "avg_points_2023_24",
      "right_output_column": "avg_points_2024_25",
      "output_metric": "increase",
      "sort": {"by": "increase", "direction": "desc"}
    }
  }
}
```

Output shape:

```json
{
  "ok": true,
  "analysis_id": "analysis_...",
  "outputs": {
    "tables": [],
    "artifacts": [],
    "findings": [
      {
        "kind": "ranked_extreme",
        "evidence_table_id": "q_2023_24.primary_q_2024_25.primary_increase",
        "row_refs": [0]
      }
    ]
  },
  "logs": [],
  "provenance": {
    "runtime": "local_trusted",
    "operation_kind": "join_and_delta",
    "parent_table_ids": ["q_2023_24.primary", "q_2024_25.primary"],
    "tool": "python_analysis.run"
  },
  "error": null
}
```

The wrapper is designed for future orchestrator use: retrieval tables come from `semantic_query.plan_execute`, derived tables come from `python_analysis.run`, and charts/tables are rendered afterward by `artifact_renderer.render`.

## Current Multi-Call Route

The orchestrator has one governed multi-call route for team average-points increases between two regular seasons.

Tool sequence:

```text
semantic_query.plan_execute(left season semantic draft)
semantic_query.plan_execute(right season semantic draft)
python_analysis.run(join_and_delta)
```

The route is a narrow acceptance path for the future open-ended orchestrator. It proves that the assistant can make multiple ontology-grounded retrieval calls and compute a derived table without raw SQL, arbitrary Python, or a model tool loop.

## Future Tools

These are planned contracts, not current behavior:

- `answer_composer.compose`: compose open-ended answers from evidence-bearing tool outputs.

The implementation should keep tool schemas plain JSON-compatible so they can later be wrapped by Responses API tool calling, Agents SDK, or another orchestration framework.
