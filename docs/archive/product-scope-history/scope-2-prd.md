# Scope 2 PRD

## Goal

Scope 2 turns the Scope 1 terminal assistant into a basic localhost web assistant.

The core promise is:

```text
one user question
-> one existing assistant pipeline run
-> one web answer
```

Scope 2 should prove that the assistant can be used through a browser without changing the semantic architecture built in Scope 1.

## Interface

Scope 2 is localhost-only.

The primary interface is a basic web page with:

- a question textbox
- a submit button
- a loading state
- a response section
- an error section
- an optional debug display

The original Scope 2 implementation direction was:

```text
local static page over the FastAPI API
```

This was a Scope 2 implementation choice, not a permanent product commitment. The product has since moved to a SvelteKit frontend in `apps/web-ui`; FastAPI is now API-only.

## User Experience

The user opens a local web page, types an NBA analytics question, submits it, and sees the answer.

Example question:

```text
Show me the top 10 players by points over the last 10 games
```

Expected behavior:

- the page shows a loading state while the assistant runs
- the page displays the final answer returned by the existing answer synthesis layer
- terminal-style tables may be rendered as preformatted text
- errors are shown clearly in the page instead of failing silently

## Backend Contract

Scope 2 should expose a small local HTTP API.

Recommended shape:

```text
POST /api/chat
```

Request:

```json
{
  "question": "Show me the top 10 players by points over the last 10 games",
  "debug": false
}
```

Response:

```json
{
  "ok": true,
  "answer": "...",
  "debug": null
}
```

Error response:

```json
{
  "ok": false,
  "error": "Could not resolve metric 'assists' against the ontology."
}
```

The exact JSON shape may evolve during implementation, but the API should preserve these ideas:

- one request represents one user question
- one response contains either one answer or one clear error
- debug information is optional
- web routes do not own semantic interpretation, planning, runtime execution, or answer synthesis logic

## Architecture Requirements

Scope 2 must reuse the Scope 1 pipeline:

```text
natural-language question
-> semantic draft
-> typed Query IR
-> ontology-grounded validation/resolution
-> execution plan
-> Python runtime result
-> answer synthesis
-> web response
```

The web layer should call a shared assistant function or existing CLI pipeline wrapper. It should not create a parallel semantic path.

The web layer must not:

- introduce web-only phrase restrictions
- hardcode supported metrics, objects, dimensions, or links
- build SQL directly
- bypass Haskell grounding
- bypass Python runtime execution
- invent analysis not present in runtime results

The same Scope 1 failure contract still applies.

## Failure Contract

Scope 2 may fail when:

- the ontology has no matching object, metric, dimension, attribute, or link
- the local data snapshot does not contain the required field/path
- the question is outside the supported assistant families
- the user question is ambiguous enough that the system cannot safely ground it
- the local web server or local assistant process is unavailable

Scope 2 should not fail because:

- the browser path supports fewer valid questions than the CLI path
- the web route has its own hardcoded allowlist
- the web route parses user language independently from the semantic interpreter
- the web response hides useful ontology/data failure messages behind generic errors

## Debug Mode

Scope 2 should include an optional debug mode.

When enabled, the page may show details such as:

- semantic draft
- typed query
- resolved query
- execution plan
- final formatted answer

Debug details should be shown as raw/preformatted JSON or text. Polished debug UI is not required for Scope 2.

## Testing Requirements

Scope 2 should include deterministic tests for the web/API path.

Tests should prove:

- the web API accepts a question and returns an answer
- the web API returns a clear error when the assistant pipeline fails
- the web route calls the shared assistant pipeline rather than duplicating semantic logic
- debug mode returns or exposes debug information when requested

Tests should avoid depending on live LLM availability unless they are explicitly marked as live/integration tests.

## Acceptance Criteria

Scope 2 is complete when:

- a developer can start a local web server
- a developer can open the local web page in a browser
- the page accepts a natural-language NBA analytics question
- the page shows a loading state while the answer is running
- the page displays the same kind of answer the CLI would return
- the page displays clear errors for unsupported or ungroundable questions
- the backend route reuses the existing Scope 1 assistant pipeline
- deterministic tests cover the API/web boundary

Primary acceptance question:

```text
Show me the top 10 players by points over the last 10 games
```

Expected result:

```text
The web page shows a ranked answer containing the top players and their points.
```

Primary error acceptance:

```text
Ask a question the ontology cannot ground.
```

Expected result:

```text
The web page shows a clear grounded error message.
```

## Non-Goals

Scope 2 does not include:

- chatbot memory inside a thread
- multi-turn conversation state
- generative UI charts
- polished dashboard UI
- authentication
- deployment
- production hosting
- production sandboxing
- streaming responses
- background jobs
- saved history
- multiple concurrent user sessions as a product feature
- replacing the Scope 1 semantic pipeline

These can be considered in later scopes after the basic localhost web assistant works.
