# Scope 4 PRD

## Goal

Scope 4 adds a Python analysis tool boundary and chart artifacts.

The core promise is:

```text
grounded SQL/runtime result
-> trusted Python analysis operation
-> structured table/chart artifacts
-> SvelteKit renders the artifacts
```

Scope 4 should prove that the assistant can produce richer analytical artifacts than a SQL result table while preserving the ontology-grounded semantic path.

## Problem Statement

Scope 1 can answer grounded analytical questions through the CLI. Scope 2 added a local browser surface. Scope 3 added structured artifacts and real table rendering.

The next product gap is that some useful analytical work is better handled after SQL:

- chart generation
- dataframe reshaping
- derived columns
- rolling averages
- percent changes
- grouped comparisons
- chart-ready series preparation

This work should not be welded directly into the SQL compiler or Svelte UI. It should exist behind a clean analysis-tool boundary so a future agent can call it as one tool among several.

## Solution

Add a provider-neutral Python analysis tool contract with a first local implementation.

The first runtime is:

```text
local_trusted_python_worker
```

This worker executes trusted Python operations owned by the codebase. It does not execute arbitrary LLM-generated Python code.

The first chart implementation is:

```text
Altair in Python
-> Vega-Lite chart spec
-> chart artifact
-> vega-embed in SvelteKit
```

The long-term commitment is not Altair or Vega-Lite forever. The commitment is the artifact boundary:

```json
{
  "kind": "chart",
  "renderer": "vega_lite",
  "title": "...",
  "spec": {},
  "data": {},
  "metadata": {}
}
```

Future renderers such as Plotly or OpenUI should be additive:

```json
{
  "kind": "chart",
  "renderer": "plotly",
  "spec": {}
}
```

```json
{
  "kind": "ui",
  "renderer": "openui",
  "spec": {}
}
```

## User Experience

A user can ask for a chart-style analytical answer.

Example:

```text
Show monthly average points for teams in the 2025-26 regular season as a chart
```

Expected response:

- text artifact explaining what was done
- table artifact containing the underlying rows
- chart artifact rendered in the browser
- clear error if the ontology/data cannot support the requested metric, dimension, time scope, or chart shape

## Architecture Requirements

Scope 4 should preserve the current grounding path:

```text
natural-language question
-> semantic draft
-> Haskell ontology grounding/planning
-> Python runtime SQL execution
-> Python analysis tool operation
-> answer/artifact packaging
-> SvelteKit rendering
```

The Python analysis tool must not:

- bypass Haskell ontology grounding
- invent metrics, dimensions, filters, or joins
- run arbitrary user/LLM Python code
- treat chart generation as frontend-only logic
- hide analysis errors behind generic chart failures

The frontend chart renderer must not:

- infer missing analytical meaning
- generate new data
- parse markdown as a chart source
- become the owner of analysis logic

## Tool Boundary

Scope 4 should introduce a tool-shaped boundary even before multi-step agent control exists.

For now, the path is deterministic:

```text
if the grounded plan/result asks for an analysis/chart operation:
  run the Python analysis tool
else:
  skip it
```

Later, an agent can choose this tool dynamically.

Recommended conceptual tool shape:

```json
{
  "tool": "python_analysis",
  "runtime": "local_trusted",
  "input": {
    "tables": []
  },
  "operation": {
    "kind": "line_chart",
    "x": "month",
    "y": "average_points",
    "series": "team"
  }
}
```

Output:

```json
{
  "ok": true,
  "artifacts": [],
  "logs": [],
  "metadata": {}
}
```

## Stack Decision

Scope 4 starts with:

```text
pandas for dataframe operations
Altair for chart specification generation
Vega-Lite JSON as the chart artifact spec
vega-embed in SvelteKit for rendering
```

Cloud sandbox APIs are out of scope for Scope 4.

Examples of future sandbox providers:

- E2B Code Interpreter
- Vercel Sandbox
- Modal Sandboxes
- Docker/firejail local isolation

These become relevant when the product needs arbitrary AI-generated Python execution.

## Failure Contract

Scope 4 may fail when:

- the ontology has no matching object, metric, dimension, attribute, value, or link
- the data snapshot cannot support the requested field, path, predicate, or time scope
- the result shape cannot support the requested chart operation
- the chart operation is outside the supported operation schema
- the local Python analysis worker fails with a clear operation error
- the browser cannot render a supported chart artifact

Scope 4 should not fail because:

- chart intent is handled only by phrase-specific corridors
- chart rendering requires markdown parsing
- Python analysis is tightly coupled to one SQL query shape
- frontend code owns analysis decisions
- unsupported chart providers leak into the core artifact contract

## Out Of Scope

Scope 4 does not include:

- arbitrary LLM-generated Python execution
- cloud sandbox provider setup
- multi-step agent tool choice
- thread memory
- OpenUI / generative UI
- Plotly renderer
- production deployment
- dashboard composition
- saved chart state
- user-authored notebooks

## Acceptance Criteria

Scope 4 is complete when:

- the codebase has a provider-neutral Python analysis operation contract
- the first local trusted Python worker can run deterministic dataframe/chart operations
- backend responses can include chart artifacts
- SvelteKit can render Vega-Lite chart artifacts
- at least one chart-intent question returns text, table, and chart artifacts
- existing non-chart questions still work
- deterministic backend and frontend tests pass

First chart capability:

- chart/graph/plot/visualization wording is treated as presentation intent
- the first supported chart shape is a grounded time-series line chart
- chart generation runs after ontology-grounded execution, using the returned table artifact as input
