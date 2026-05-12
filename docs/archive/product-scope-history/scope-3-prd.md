# Scope 3 PRD

## Goal

Scope 3 turns the Scope 2 localhost web assistant from a terminal-text renderer into a structured artifact UI.

The core promise is:

```text
one user question
-> one existing assistant pipeline run
-> structured answer artifacts
-> SvelteKit renders those artifacts as real UI
```

Scope 3 should prove that the browser can render assistant results as product UI without changing the ontology-grounded semantic path built in Scope 1 and reused in Scope 2.

## Problem Statement

Scope 2 proves that the assistant can be used in a browser, but the browser currently displays the final answer as preformatted text.

That is useful for proving the path works, but it is not the long-term product shape. Tables should not be parsed back out of markdown. Charts should not be bolted onto a text blob. Future Python sandbox outputs, generated files, debug traces, and tool-call results should not depend on one hardcoded answer order.

The product needs a cleaner boundary:

```text
execution and synthesis produce structured artifacts
presentation renders those artifacts
```

## Solution

Build a SvelteKit + TypeScript frontend that calls the existing local assistant API and renders structured response artifacts.

The first supported artifact types are:

- `text`: the user-facing narrative answer, interpretation, assumptions, and caveats
- `table`: typed columns and rows rendered with TanStack Table
- `debug`: optional developer-facing pipeline details

Scope 3 should preserve the Scope 2 one-question flow:

```text
ask one question
wait for one assistant run
receive one response
render answer artifacts
```

The implementation direction is:

```text
FastAPI assistant API stays
SvelteKit + TypeScript becomes the browser UI
TanStack Table renders table artifacts
artifact contracts stay framework-neutral
```

## User Experience

The user opens the local web app, types a natural-language NBA analytics question, submits it, and sees a polished answer.

For a ranking/table question, the page should show:

- the interpreted answer text
- a real interactive table
- column labels with useful formatting
- fixed-height table area with vertical scroll
- horizontal scroll for wide results
- sticky table header
- client-side column sorting
- row count / displayed row count
- clear loading and error states

Example question:

```text
Show me the top 10 players by points over the last 10 games
```

Expected UI result:

```text
Interpreted as: players ranked by points over the last 10 games.

[interactive table]
Player | Team | Games Played | Points
...
```

## Artifact Contract

Scope 3 should introduce a web-facing response shape that can carry both the existing formatted answer and structured artifacts.

Recommended response shape:

```json
{
  "ok": true,
  "answer": "...",
  "artifacts": [
    {
      "kind": "text",
      "role": "summary",
      "text": "..."
    },
    {
      "kind": "table",
      "title": "Top players by points",
      "columns": [
        {
          "id": "player",
          "label": "Player",
          "type": "text"
        },
        {
          "id": "points",
          "label": "Points",
          "type": "number"
        }
      ],
      "rows": [
        {
          "player": "Jalen Brunson",
          "points": 312
        }
      ],
      "row_count": 10
    }
  ],
  "debug": null
}
```

The exact JSON may evolve during implementation, but the contract should preserve these ideas:

- artifacts are ordered, but renderers should not assume only one artifact exists
- table artifacts contain real columns and rows, not markdown
- column types are explicit enough for formatting and sorting
- the existing `answer` string remains available for CLI compatibility and fallback rendering
- debug is optional and separate from user-facing artifacts

## Architecture Requirements

Scope 3 must reuse the existing assistant path:

```text
natural-language question
-> semantic draft
-> typed Query IR
-> ontology-grounded validation/resolution
-> execution plan
-> Python runtime result
-> answer synthesis
-> artifact packaging
-> SvelteKit rendering
```

The SvelteKit layer is a presentation adapter. It must not become a second assistant brain.

The frontend must not:

- interpret natural-language questions
- hardcode supported metrics, objects, dimensions, attributes, or links
- build SQL
- bypass Haskell grounding
- bypass Python runtime execution
- parse markdown tables as the primary table path
- invent analysis not present in runtime or synthesis results

The backend artifact packaging layer may transform existing runtime/synthesis payloads into UI artifacts, but it must stay grounded in actual results.

## Stack Decision

Scope 3 commits to:

```text
SvelteKit
TypeScript
TanStack Table for table artifacts
FastAPI backend kept as the assistant API
```

This stack is chosen because:

- SvelteKit is a good fit for custom, product-specific analytical UI
- TypeScript gives the artifact contract compile-time shape on the frontend
- TanStack Table gives strong table behavior without building a grid from scratch
- FastAPI already owns the local assistant boundary and does not need to be replaced
- the artifact contract keeps future chart and sandbox renderers modular

## Failure Contract

Scope 3 may fail when:

- the ontology has no matching object, metric, dimension, attribute, or link
- the local data snapshot does not contain the required field/path
- the question is outside the supported assistant families
- the user question is ambiguous enough that the system cannot safely ground it
- the local assistant API is unavailable
- the artifact payload is malformed

Scope 3 should not fail because:

- the SvelteKit path supports fewer valid questions than the CLI path
- the frontend has its own hardcoded semantic allowlist
- the frontend tries to parse answer text instead of using structured artifacts
- the table renderer cannot handle wide or tall tables
- the UI hides useful ontology/data errors behind generic browser messages

## Out Of Scope

Scope 3 does not include:

- multi-step chatbot memory
- Python sandbox execution
- chart generation
- generative UI components created by the model
- authentication
- production deployment
- collaborative notebooks
- persistent conversation history
- replacing FastAPI
- replacing the CLI

These are future scopes that should build on the artifact boundary rather than being mixed into the first structured UI slice.

## Testing Requirements

Scope 3 should include deterministic tests for:

- artifact response packaging
- table artifact shape
- API backward compatibility for existing `answer`
- SvelteKit component rendering with sample artifacts
- table sorting behavior
- loading and error states

Tests should avoid live LLM dependency unless explicitly marked as live/integration tests.

## Acceptance Criteria

Scope 3 is complete when:

- a developer can start the FastAPI assistant API
- a developer can start the SvelteKit frontend
- the browser can submit a natural-language NBA analytics question
- the answer renders as structured UI artifacts
- table results render through TanStack Table, not markdown parsing
- the existing CLI still works
- the Scope 2 API path still has a compatibility story
- deterministic tests pass for backend artifacts and frontend rendering
