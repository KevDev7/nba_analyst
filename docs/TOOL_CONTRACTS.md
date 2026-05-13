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
  "question_context": "string or null",
  "semantic_draft_state": "raw",
  "mode": "plan_and_execute",
  "row_limit": 500,
  "include_debug": false,
  "include_private_sql": false,
  "caller": "orchestrator"
}
```

Validation:

- Exactly one of `question` or `semantic_draft` is required.
- Direct `semantic_draft` inputs default to `semantic_draft_state: "raw"` and are prepared through deterministic assumptions/entity resolution before Haskell planning.
- Internally generated drafts that already include deterministic defaults can use `semantic_draft_state: "prepared"`.
- `mode` is currently only `plan_and_execute`.
- `row_limit` is enforced at the runtime result boundary and recorded in provenance.
- `include_private_sql` is honored only when `include_debug` is true, `NBA_ALLOW_PRIVATE_SQL_TRACE` is enabled, and the caller is trusted.

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
        "row_count": 10,
        "returned_row_count": 10,
        "row_limit_requested": 500,
        "row_limit_enforced": true,
        "truncated": false,
        "execution_ms": 83
      }
    ],
    "row_limit_requested": 500,
    "row_limit_enforced": true,
    "default_scope_source": "snapshot_metadata",
    "default_season_year": "2025-26",
    "default_season_type": "regular_season"
  },
  "trace": {},
  "debug": null,
  "error": null
}
```

`tables` are built from the typed `FinalAnswer`/runtime payload, not scraped from UI artifacts. Artifacts remain presentation outputs; downstream analysis should consume `tables`.

Default season and season-type policy is now read from the local snapshot metadata when available, with the previous constants retained as fallbacks. Normal traces record the default-scope source and values so future default changes are auditable without changing answer wording.

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

- prefers Haskell `inspect-ontology-json` over the validated ontology model;
- falls back to reading `fixtures/ontology/semantic-gold.yaml`;
- reads coverage metadata from `fixtures/duckdb/gold_slice.duckdb`;
- returns ontology and snapshot hashes;
- does not replace Haskell ontology validation.

Input shape:

```json
{
  "facets": ["subjects", "fact_surfaces", "metrics", "dimensions", "filters", "time_grains", "coverage"],
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
  "subjects": [
    {"key": "Team", "label": "Team"}
  ],
  "fact_surfaces": [
    {"key": "TeamGame", "subject": "Team", "grain": "game"}
  ],
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
  "answer": "<FinalAnswer object or null>",
  "tables": ["<AnalysisTable objects>"],
  "summary": "optional summary for table-only rendering",
  "interpretation": "optional interpretation for table-only rendering",
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
It can now render either grounded `FinalAnswer` payloads or derived `AnalysisTable` outputs.

### `python_analysis.run`

Purpose: run controlled derived analysis over approved input tables. This is not arbitrary Python execution and does not receive a database handle.

Current controlled operations:

- `join_and_delta`: joins two tables on declared keys and computes `right_metric - left_metric`.
- `rank_extremes`: sorts one table by a numeric metric and adds a deterministic rank column.
- `correlation`: joins two tables on declared keys and computes a Pearson correlation over matched numeric columns.
- chart operations remain available through the same runtime contract for artifact generation.
- `python_code`: gated sandbox prototype for custom derived analysis over approved tables only.

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
    "metrics": [],
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
    "derived_from_table_ids": ["q_2023_24.primary", "q_2024_25.primary"],
    "output_table_ids": ["q_2023_24.primary_q_2024_25.primary_increase"],
    "tool": "python_analysis.run"
  },
  "error": null
}
```

The wrapper is designed for future orchestrator use: retrieval tables come from `semantic_query.plan_execute`, derived tables come from `python_analysis.run`, and charts/tables are rendered afterward by `artifact_renderer.render`.

Correlation plans use the same governed path: retrieve each metric through `semantic_query.plan_execute`, compute the relationship through the controlled `correlation` operation, then render the derived result through `artifact_renderer.render`.

#### Gated `python_code` Operation

`python_code` is disabled by default and requires:

```text
NBA_ENABLE_PYTHON_CODE_SANDBOX=1
```

It is not a retrieval boundary. It receives only approved input tables that were already produced by governed retrieval or prior governed analysis.

Input shape:

```json
{
  "tool": "python_analysis",
  "runtime": "local_sandbox",
  "tables": [
    {
      "id": "approved.players",
      "columns": [
        {"id": "player", "label": "Player", "type": "text"},
        {"id": "points", "label": "Points", "type": "number"}
      ],
      "rows": []
    }
  ],
  "operation": {
    "kind": "python_code",
    "code": "rows = tables['approved.players']['rows']\noutputs['tables'] = [...]",
    "input_table_ids": ["approved.players"],
    "output_tables": [
      {
        "id": "analysis.out",
        "columns": [
          {"id": "player", "label": "Player", "type": "text"},
          {"id": "points", "label": "Points", "type": "number"}
        ]
      }
    ],
    "policy": {
      "max_input_rows": 5000,
      "max_output_rows": 500,
      "timeout_ms": 5000,
      "memory_mb": 256,
      "import_allowlist": ["math", "statistics", "json"],
      "no_network": true,
      "no_filesystem_except_scratch": true,
      "no_environment_access": true
    }
  }
}
```

Normal provenance exposes `code_hash`, parent table ids, output table ids, runtime id, timeout state, stdout, and stderr. Raw SQL is never supplied to the sandbox.

The local prototype uses a subprocess plus macOS `sandbox-exec` when available. The Python layer also rejects forbidden imports and calls such as `duckdb`, `sqlite3`, `socket`, `requests`, `urllib`, `os`, `subprocess`, `pathlib`, `open`, `eval`, `exec`, `compile`, and environment access.

## Current Multi-Call Route

The orchestrator has a deterministic period-delta route for explicit season-over-season metric increases.

Tool sequence:

```text
semantic_query.plan_execute(left season semantic draft)
semantic_query.plan_execute(right season semantic draft)
python_analysis.run(join_and_delta)
artifact_renderer.render(derived AnalysisTable)
```

The route lives under `apps/assistant/routes/period_delta.py` and uses a structured `PeriodDeltaPlan`. It proves that the assistant can make multiple ontology-grounded retrieval calls, compute a derived table, and render artifacts without raw SQL, arbitrary Python, or a model tool loop.

## Gated Model Orchestration

Model orchestration is disabled by default. It can be enabled for controlled testing with:

```text
NBA_ENABLE_MODEL_ORCHESTRATOR=1
```

Dry-run mode can be enabled with:

```text
NBA_MODEL_ORCHESTRATOR_DRY_RUN=1
```

Dry-run mode validates a model-produced plan and returns the planned tool sequence, but it does not execute tools.

Allowed plan kinds:

- `simple_semantic_query`
- `period_delta`
- `artifact_request`
- `unsupported`

Allowed model-plan tool names:

- `ontology_catalog.inspect`
- `semantic_query.plan_execute`
- `python_analysis.run`
- `artifact_renderer.render`

Forbidden tool names and references include:

- `raw_sql`
- `raw_python`
- `sql.execute`
- `duckdb.execute`
- direct `python_code` plan references outside the gated `python_analysis.run` operation contract

The model orchestrator may produce a structured plan, choose governed tools, and request artifacts. It must not author SQL, request a database handle, or claim support for unsupported surfaces such as play-by-play, lineups, on-off, clutch, or shot location. It does not get a separate raw Python/code tool; any future code-mode analysis must be routed through `python_analysis.run` and the sandbox gate.

## Grounded Answer Composer

The model-assisted answer composer is disabled by default and can be enabled only alongside model orchestration:

```text
NBA_ENABLE_MODEL_ANSWER_COMPOSER=1
```

Input is limited to:

- structured evidence tables;
- derived findings;
- artifact summaries.

The composer does not receive raw SQL, execution plans, database handles, hidden planner output, or arbitrary files.

Output shape:

```json
{
  "answer": "The Magic had the largest increase.",
  "claims": [
    {
      "text": "The Magic increased by 5.6.",
      "evidence_refs": [
        {
          "table_id": "analysis.delta",
          "row_index": 0,
          "columns": ["entity", "delta"]
        }
      ]
    }
  ],
  "limitations": []
}
```

Validation:

- every claim must include evidence refs;
- each evidence table id must exist;
- each row index must be in range;
- each referenced column must exist on the row;
- numeric claim text must match a numeric referenced value where feasible;
- entity/name claim text must match referenced text evidence where feasible;
- unsupported causal wording such as "caused by", "because of", or "drove" is rejected unless a future causal evidence contract exists;
- invalid composed output is retried once;
- invalid model output falls back to the deterministic answer.

## Future Tools

These are planned contracts, not current behavior:

- a richer set of controlled analysis operations before relying on arbitrary code.

The implementation should keep tool schemas plain JSON-compatible so they can later be wrapped by Responses API tool calling, Agents SDK, or another orchestration framework.
