# Scope 4 Implementation Plan

This plan explains how to implement the Scope 4 PRD.

The PRD defines what "done" means. This file defines the implementation path.

## Target

Scope 4 is complete when the assistant can deterministically produce chart artifacts through a Python analysis tool boundary:

```text
grounded SQL/runtime result
-> local trusted Python analysis worker
-> chart/table/text artifacts
-> SvelteKit renders the artifacts
```

The analysis worker should be tool-shaped so future multi-step agents can call it, but Scope 4 should not introduce agent-controlled tool choice yet.

## Vertical Slices

Scope 4 should be implemented as four vertical slices.

## Slice 1: Analysis Tool Contract

Goal:

Define the provider-neutral Python analysis tool contract without adding real chart generation yet.

Primary behavior:

```text
analysis input + operation spec
-> validated analysis request
-> structured analysis result shape
```

Likely files:

- `services/runtime-py/runtime/AnalysisTools/`
- `services/runtime-py/runtime/AnalysisTools/models.py`
- `services/runtime-py/runtime/AnalysisTools/contracts.py`
- `tests/test_analysis_tool_contract.py`

Work:

- Add typed models for analysis input tables.
- Add typed models for operation specs.
- Add typed models for analysis results, logs, errors, and artifacts.
- Include chart artifact model with provider-neutral fields:
  - `kind`
  - `renderer`
  - `title`
  - `spec`
  - `data`
  - `metadata`
- Keep this independent from any one chart library.

Done when:

- contract tests pass
- no assistant behavior changes yet
- existing artifact/table path remains unchanged

Verification:

```bash
python3 -m unittest tests.test_analysis_tool_contract
python3 -m compileall services/runtime-py/runtime tests
```

## Slice 2: Local Trusted Python Worker

Goal:

Add the first implementation of the analysis tool using trusted local Python code.

Primary behavior:

```text
structured table input
-> pandas dataframe operation
-> structured output artifacts
```

Likely files:

- `services/runtime-py/runtime/AnalysisTools/local_worker.py`
- `services/runtime-py/runtime/AnalysisTools/operations.py`
- `services/runtime-py/runtime/AnalysisTools/models.py`
- `tests/test_local_analysis_worker.py`

Work:

- Convert structured rows to pandas dataframes.
- Run controlled operation specs only.
- Return structured results and logs.
- Do not execute arbitrary Python strings.
- Start with simple dataframe operations needed for chart generation.

Done when:

- local worker can accept a table and return a deterministic transformed result
- unsupported operations fail clearly
- no arbitrary code execution exists

Verification:

```bash
python3 -m unittest tests.test_local_analysis_worker tests.test_analysis_tool_contract
python3 -m compileall services/runtime-py/runtime tests
```

## Slice 3: Vega-Lite Chart Artifact + Svelte Renderer

Goal:

Add the first chart artifact renderer.

Primary behavior:

```text
chart artifact with renderer = vega_lite
-> SvelteKit renders chart using vega-embed
```

Likely files:

- backend chart artifact tests
- `apps/web-ui/package.json`
- `apps/web-ui/src/lib/artifacts/ChartArtifact.svelte`
- `apps/web-ui/src/lib/artifacts/ArtifactRenderer.svelte`
- `apps/web-ui/src/lib/artifacts/types.ts`
- `apps/web-ui/src/lib/charts/`
- frontend tests for chart artifact dispatch

Work:

- Add `chart` artifact TypeScript type.
- Add `vega-embed` dependency.
- Add chart renderer component.
- Render Vega-Lite specs from artifact payloads.
- Show a clear unsupported-renderer message for unknown chart renderers.

Done when:

- SvelteKit can render a sample Vega-Lite chart artifact
- text/table artifacts still render
- unknown chart renderer does not crash the page

Verification:

```bash
npm --prefix apps/web-ui run check
npm --prefix apps/web-ui run test
npm --prefix apps/web-ui run build
python3 -m unittest tests.test_analysis_tool_contract
```

## Slice 4: One End-To-End Chart Capability

Goal:

Wire one deterministic chart-intent path through the existing assistant pipeline.

Primary behavior:

```text
chart-intent user question
-> grounded query/runtime rows
-> local analysis worker builds chart artifact
-> response includes text + table + chart artifacts
-> SvelteKit renders all three
```

Example acceptance question:

```text
Show monthly average points for teams in the 2025-26 regular season as a chart
```

Likely files:

- semantic interpreter prompt/schema if chart intent needs to be transported
- Haskell planning/execution plan if chart intent becomes plan metadata
- Python runtime models if analysis steps are added to execution plans
- analysis worker files from slices 1-2
- answer/artifact packaging files
- SvelteKit chart renderer files
- new backend/runtime tests
- new deterministic CLI or API tests with mocked LLM

Work:

- Treat chart wording as presentation intent after semantic grounding.
- Keep query grounding ontology-backed.
- Feed grounded time-series table artifacts into the local analysis worker.
- Merge returned chart artifact into response artifacts.
- Preserve existing answer string and table artifacts.

Current first chart path:

- user asks for a chart/graph/plot/visualization
- grounded result shape is `time_series`
- table artifact has a time/date x-axis and numeric metric column
- assistant appends a Vega-Lite line chart artifact before the table artifact
- unsupported chart shapes keep the grounded text/table answer instead of failing the whole response

Done when:

- at least one chart-intent question returns chart artifacts end to end
- non-chart questions continue to return text/table artifacts
- failures are grounded in ontology/data/product-scope limits, not arbitrary missing transport fields

Verification:

```bash
python3 -m unittest tests.test_analysis_tool_contract tests.test_local_analysis_worker tests.test_web_api tests.test_answer_artifacts
npm --prefix apps/web-ui run check
npm --prefix apps/web-ui run test
npm --prefix apps/web-ui run build
python3 -m compileall apps/assistant apps/web services/runtime-py/runtime tests
git diff --check
```

Optional live smoke:

```bash
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000
scripts/run_web_ui_portless.sh
```

Then ask:

```text
Show monthly average points for teams in the 2025-26 regular season as a chart
```

## Guardrails

Scope 4 implementation must preserve these rules:

- The Python analysis tool is a tool boundary, not an arbitrary code executor.
- The analysis worker must not invent ontology concepts.
- The frontend renders chart artifacts; it does not decide analytical meaning.
- Chart artifacts should be renderer-neutral at the contract level.
- Vega-Lite is the first renderer, not the permanent only renderer.
- Cloud sandbox providers are out of scope until arbitrary AI-generated code is explicitly supported.
