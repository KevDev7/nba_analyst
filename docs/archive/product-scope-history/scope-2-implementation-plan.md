# Scope 2 Implementation Plan

This plan explains how to implement the Scope 2 PRD.

The PRD defines what "done" means. This file defines the implementation path.

## Target

Scope 2 is complete when a developer can use the assistant through a localhost web page:

```text
browser question
-> local web API
-> existing Scope 1 assistant pipeline
-> web response
```

The web path must reuse the Scope 1 semantic pipeline. It should not create a second interpretation, planning, runtime, or answer-synthesis path.

## Vertical Slice

Scope 2 should be implemented as one vertical slice, not five separate slices:

```text
Localhost Web Assistant
```

This slice should go from browser input to rendered browser answer in one pass.

The work has multiple engineering tasks, but they all serve one acceptance path:

```text
open localhost
type question
click submit
see loading state
see answer or clear error
optionally inspect debug details
```

It should only be split into more vertical slices if implementation becomes larger than expected.

## Slice 1: Localhost Web Assistant

Goal:

Add a basic localhost web interface over the existing Scope 1 assistant pipeline.

Acceptance behavior:

```text
open localhost
type question
click submit
see loading state
see answer or clear error
```

Primary acceptance question:

```text
Show me the top 10 players by points over the last 10 games
```

Expected result:

```text
The web page shows the same kind of ranked answer the CLI would return.
```

## Internal Work Areas

These are implementation tasks inside the one vertical slice.

They are not separate vertical slices. They are just the order of work needed to complete the single browser-to-answer path.

### A. Shared Assistant Boundary

Files:

- `apps/cli/main.py`
- possible new shared module under `apps/cli/` or `apps/assistant/`

Work:

- Expose a reusable function for one question to one answer.
- Preserve the existing CLI behavior.
- Return structured success/error/debug data for web usage.
- Keep semantic interpretation, Haskell planning, runtime execution, and answer synthesis in the existing pipeline.
- Keep CLI as a terminal adapter over the shared boundary.

Done when:

- CLI still works the same way.
- web/API code can call the shared boundary.
- no semantic logic moves into web-specific code.

### B. Local API Endpoint

Files:

- possible new `apps/web/server.py`
- possible new `apps/web/models.py`
- possible new `tests/test_web_api.py`

Work:

- Add a localhost FastAPI app.
- Add `POST /api/chat`.
- Accept a question and optional debug flag.
- Validate that question is present and non-empty.
- Call the shared assistant boundary.
- Return clear JSON for success and failure.

Expected API shape:

```text
POST /api/chat
{"question": "...", "debug": false}
-> {"ok": true, "answer": "..."}
```

Done when:

- API route can return an answer.
- API route can return a clear error.
- API route does not contain semantic interpretation, planning, SQL, or answer synthesis logic.

### C. Simple HTML/JS Frontend

Files:

- `apps/web/server.py`
- possible `apps/web/static/index.html`
- possible `apps/web/static/app.js`
- possible `apps/web/static/styles.css`

Work:

- Serve a single HTML page from the FastAPI app.
- Add textbox and submit button.
- Call `POST /api/chat` from browser JavaScript.
- Show a loading state.
- Render the answer as preformatted text.
- Show errors clearly.

Done when:

- a developer can open the page locally.
- a submitted question reaches the API.
- the answer appears on the page.
- errors appear on the page.

### D. Debug Display

Files:

- `apps/web/server.py`
- web page JS/HTML
- shared assistant response shape

Work:

- Add a debug checkbox or equivalent control.
- When enabled, show semantic draft, query, resolved query, execution plan, and final answer if available.
- Render debug output as raw/preformatted text or JSON.
- Keep debug UI simple.

Done when:

- debug output is visible only when requested.
- debug output helps inspect the same stages as CLI `--debug`.

### E. Deterministic Web Regression Tests

Files:

- possible new `tests/test_web_api.py`
- existing test helpers if useful

Work:

- Add API success test.
- Add API failure test.
- Add debug-response test.
- Add a test proving the API calls the shared assistant boundary.
- Avoid live LLM dependency in Scope 2 deterministic tests.

Done when:

- deterministic web/API tests pass locally.
- existing focused CLI/semantic tests still pass.
- `python3 -m compileall apps/cli services/runtime-py/runtime tests` passes.

## Verification

At the end of Scope 2, run:

```bash
python3 -m unittest tests.test_web_api
python3 -m unittest tests.test_cli_pipeline tests.test_semantic_interpreter tests.test_semantic_draft_grounding
python3 -m compileall apps/cli services/runtime-py/runtime tests
cabal build -v0 ontology-hs
git diff --check
```

If broader test discovery still includes live-provider or stale snapshot tests, keep those failures documented separately from Scope 2 deterministic verification.

## Guardrails

Scope 2 implementation must preserve these rules:

- The web layer is an adapter, not a new assistant brain.
- The web layer must not introduce web-only semantic restrictions.
- The web layer must not build SQL.
- The web layer must not bypass Haskell grounding.
- The web layer must not bypass Python runtime execution.
- The web layer must not invent final analysis.
- The web layer should be replaceable by another frontend stack later.
