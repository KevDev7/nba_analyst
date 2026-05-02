# Scope 3 Implementation Plan

This plan explains how to implement the Scope 3 PRD.

The PRD defines what "done" means. This file defines the implementation path.

## Target

Scope 3 is complete when a developer can use a SvelteKit browser UI that renders structured assistant artifacts:

```text
browser question
-> local assistant API
-> existing ontology-grounded assistant pipeline
-> structured artifacts
-> SvelteKit renders text and table artifacts
```

The frontend should become richer without becoming a second semantic path.

## Vertical Slices

Scope 3 should be implemented as three vertical slices.

These are real vertical slices, not just chores. Each one should leave the project in a working state.

## Slice 1: Artifact Contract And Backend Packaging

Goal:

Add a framework-neutral artifact contract to the backend while preserving the existing text answer.

Primary behavior:

```text
POST /api/chat
-> answer string still exists
-> artifacts array exists
-> table-like answers include table artifacts when possible
```

Likely files:

- `apps/web/models.py`
- `apps/web/server.py`
- `apps/assistant/pipeline.py`
- possible new `apps/assistant/artifacts.py`
- possible new `tests/test_answer_artifacts.py`
- existing answer synthesis/runtime model files if the cleanest artifact source is there

Work:

- Define artifact models for `text`, `table`, and `debug`.
- Keep the existing `answer` field for CLI/web compatibility.
- Package text artifacts from the synthesized answer.
- Package table artifacts from structured runtime/synthesis payloads where available.
- Avoid parsing markdown tables as the primary implementation.
- If full table extraction is not yet available from structured payloads, expose a narrow fallback explicitly marked as temporary in code/docs, then remove it in a later hardening step.

Done when:

- existing web API callers still receive `answer`
- new web API callers can read `artifacts`
- table-capable questions produce table artifacts from structured results
- deterministic backend tests pass

Verification:

```bash
python3 -m unittest tests.test_web_api tests.test_answer_artifacts
python3 -m compileall apps/assistant apps/web tests
```

## Slice 2: SvelteKit Frontend Shell

Goal:

Replace the static HTML/JS browser UI with a SvelteKit + TypeScript frontend shell that calls the assistant API and renders artifact cards.

Primary behavior:

```text
open local SvelteKit app
type question
submit
see loading state
see text artifact or clear error
```

Likely files/folders:

- new frontend app folder, likely `apps/web-ui/`
- `apps/web-ui/package.json`
- `apps/web-ui/svelte.config.js`
- `apps/web-ui/tsconfig.json`
- `apps/web-ui/src/routes/+page.svelte`
- `apps/web-ui/src/lib/api.ts`
- `apps/web-ui/src/lib/artifacts/types.ts`
- `apps/web-ui/src/lib/artifacts/ArtifactRenderer.svelte`

Work:

- Scaffold a SvelteKit TypeScript app.
- Configure it to call the existing FastAPI API.
- Define TypeScript types that mirror the backend artifact contract.
- Add a question input, submit button, loading state, answer area, and error area.
- Render `text` artifacts first.
- Keep the old FastAPI static page only if it is useful as a compatibility fallback; otherwise document the new dev command clearly.

Done when:

- SvelteKit frontend can submit a question to FastAPI.
- response text renders from artifacts when available.
- errors render clearly.
- old CLI behavior is unchanged.

Verification:

```bash
npm --prefix apps/web-ui run check
npm --prefix apps/web-ui run test
python3 -m unittest tests.test_web_api tests.test_answer_artifacts
```

## Slice 3: TanStack Table Artifact Renderer

Goal:

Render table artifacts as real interactive tables using TanStack Table.

Primary behavior:

```text
ask a table-producing question
-> receive table artifact
-> render fixed-height, scrollable, sortable table
```

Likely files:

- `apps/web-ui/src/lib/artifacts/TableArtifact.svelte`
- `apps/web-ui/src/lib/artifacts/ArtifactRenderer.svelte`
- `apps/web-ui/src/lib/artifacts/types.ts`
- `apps/web-ui/src/lib/table/format.ts`
- frontend tests for table rendering/sorting

Work:

- Install and configure TanStack Table Core.
- Use TanStack Core directly because the current Svelte adapter targets older
  Svelte peer versions while the app uses Svelte 5.
- Render column labels from artifact metadata.
- Use column types for alignment and formatting.
- Add fixed-height table viewport with vertical scroll.
- Add horizontal scroll for wide tables.
- Add sticky table header.
- Add client-side sort by column header.
- Preserve backend/server order by default before the user sorts.
- Show row count and displayed row count.
- Render null values consistently.

Done when:

- table artifact renders without markdown parsing.
- user can sort columns in the browser.
- wide/tall tables remain usable.
- text-only answers still render cleanly.

Verification:

```bash
npm --prefix apps/web-ui run check
npm --prefix apps/web-ui run test
python3 -m unittest tests.test_web_api tests.test_answer_artifacts
```

## Guardrails

Scope 3 implementation must preserve these rules:

- The frontend is an artifact renderer, not a semantic interpreter.
- The frontend must not introduce ontology-independent restrictions.
- The frontend must not build SQL.
- The frontend must not infer unsupported metrics, dimensions, filters, or joins.
- The frontend must not depend on parsing markdown tables as the main table path.
- The backend artifact packager must stay grounded in runtime/synthesis results.
- The artifact contract should stay framework-neutral so future renderers can be React, Svelte, CLI, or something else.

## Suggested Dev Commands

The exact commands may change during implementation, but the target developer experience should be:

```bash
# terminal 1
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000

# terminal 2
npm --prefix apps/web-ui run dev
```

If the repo standardizes on a different package manager, update this plan with the chosen commands.

## Final Verification

At the end of Scope 3, run:

```bash
python3 -m unittest tests.test_web_api tests.test_answer_artifacts
python3 -m compileall apps/assistant apps/web tests
npm --prefix apps/web-ui run check
npm --prefix apps/web-ui run test
git diff --check
```

Optional live smoke test:

```bash
python3 apps/cli/main.py "Show me the top 10 players by points over the last 10 games"
```

Then use the browser UI with the same question and confirm that the table renders as a table artifact.
