# Security And Product Review

## Final Review Checklist

- [x] Haskell-only SQL is documented as a permanent product invariant.
- [x] No public/model-visible raw SQL tool exists.
- [x] Runtime SQL governance records hashes and execution metadata without
      exposing SQL.
- [x] `python_code` is disabled by default.
- [x] E2B live tests are optional and env-gated.
- [x] Model orchestration is disabled by default.
- [x] Model tool loop remains beta and explicitly gated.
- [x] Deterministic fast path remains the default route.
- [x] Unsupported surfaces are represented as grounded limitations.
- [x] Answer composer validates evidence and falls back on invalid claims.
- [x] Safe trace summaries redact raw SQL/private debug.

## Default Production Status

Production-ready:

- deterministic fast path;
- Haskell ontology planning/retrieval;
- runtime SQL execution governance metadata;
- ontology catalog inspection;
- artifact renderer;
- controlled Python analysis operations;
- trace/eval guardrails;
- config/rollback docs.

Gated beta:

- structured model orchestration;
- iterative model tool loop;
- model answer composer;
- `python_code` sandbox;
- E2B cloud sandbox backend.

Explicitly out of scope:

- model/user/Python-authored SQL;
- public raw SQL/debug exposure;
- direct DB/DuckDB access from sandbox/model/Python analysis;
- making arbitrary code execution default-on;
- replacing the Haskell ontology planner.
