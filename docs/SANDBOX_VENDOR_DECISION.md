# Sandbox Vendor Decision

## Decision Summary

Use **E2B as the primary Slice 18 production sandbox candidate** because
`python_analysis.run` lives in the Python/FastAPI runtime and E2B exposes a
Python SDK with first-class sandbox creation, command execution, filesystem
APIs, timeouts, metrics, and network controls.

Keep **Vercel Sandbox as the strongest alternative** if the production sandbox
broker moves into a Vercel/TypeScript service or if the team chooses Vercel's
Firecracker microVM platform for operational reasons.

Keep the current `macos_sandbox_exec` backend as **local/beta-only**, disabled
by default. Do not expose it as production isolation.

No vendor SDK is added in this slice.

## Requirements

| Requirement | Why It Matters |
| --- | --- |
| Python execution over approved input tables only | Code mode is derived analysis, not retrieval. |
| No DuckDB/database access | Haskell-only SQL is permanent. |
| No raw SQL | Sandbox code must not author, repair, or transform SQL. |
| No network by default | Prevent exfiltration and hidden data retrieval. |
| No environment variable exposure | Prevent credential leaks. |
| No host filesystem exposure | Prevent local/server data reads. |
| Timeout/resource limits | Prevent runaway workloads. |
| Structured stdout/stderr capture | Debuggability and trace provenance. |
| Declared output schema validation | Answer composer needs typed evidence tables. |
| Code hash/provenance | Reproducibility and auditability. |
| Local dev and CI testability | Feature gates need deterministic tests without credentials. |
| Render/Python deployment fit | Current backend is Python/FastAPI deployed via Render. |
| Fallback when credentials are absent | Public runtime must fail closed, not silently use unsafe local code. |

## Vercel Sandbox Assessment

Sources:

- [Vercel Sandbox overview](https://vercel.com/sandbox)
- [Vercel Sandbox firewall docs](https://vercel.com/docs/vercel-sandbox/concepts/firewall)
- [Vercel Sandbox pricing and limits](https://vercel.com/docs/vercel-sandbox/pricing)

Strengths:

- Firecracker microVM isolation is a strong production boundary for untrusted
  code.
- Supports Python 3.13 runtime.
- Network policy can be set to `deny-all` at sandbox creation.
- Network policy can also be updated after setup, which supports a safe pattern
  of installing dependencies first and locking down before untrusted execution.
- Pricing has a useful free Hobby allowance and clear usage dimensions.
- Purpose-built for AI-generated and user-generated code execution.

Risks / fit issues for this repo:

- The documented SDK path is TypeScript/`@vercel/sandbox`, while
  `python_analysis.run` currently lives in Python. A direct integration would
  likely require a small TypeScript broker service, CLI bridge, or API wrapper.
- The current production backend is Render/FastAPI, not a Vercel-hosted
  TypeScript service.
- Network access defaults must be handled carefully; the backend must create
  sandboxes with deny-all before running model/user code.

Verdict:

Very strong isolation and platform story, but more integration friction for the
current Python runtime. Prefer it if the sandbox broker becomes a TypeScript
service or if production deployment moves closer to Vercel infrastructure.

## E2B Assessment

Sources:

- [E2B Python Sandbox SDK reference](https://e2b.dev/docs/sdk-reference/python-sdk/v2.3.3/sandbox_sync)
- [E2B internet access controls](https://e2b.dev/docs/sandbox/internet-access)
- [E2B pricing](https://e2b.dev/pricing)

Strengths:

- Python SDK fits the current `services/runtime-py` and FastAPI/Render backend.
- Sandbox creation supports timeouts and metrics.
- Internet access can be disabled at creation with `allow_internet_access=False`.
- More granular network allow/deny rules are available when needed.
- E2B is designed around code interpreter / AI-agent sandbox use cases.
- Free Hobby tier includes one-time usage credits, which is useful for
  integration testing.

Risks / fit issues:

- Internet is enabled by default, so Slice 18 must always create sandboxes with
  deny-out / `allow_internet_access=False`.
- The backend must pass no `envs` except non-secret execution scaffolding; code
  should receive serialized table payloads only.
- Pricing model and concurrency are different from Vercel's; production budget
  still needs explicit owner approval before enabling user-facing code mode.

Verdict:

Best production candidate for the current repo because it avoids a Node bridge
and keeps the sandbox backend behind the existing Python analysis tool boundary.

## Recommended Slice 18 Shape

Add a pluggable backend interface without changing public API shape:

```python
class SandboxBackend(Protocol):
    backend_id: str
    production_ready: bool

    def run_python_code(
        self,
        *,
        code: str,
        input_tables: list[dict[str, object]],
        output_schemas: list[dict[str, object]],
        policy: dict[str, object],
    ) -> SandboxExecutionResult:
        ...
```

Concrete backends:

- `local_beta`: existing `macos_sandbox_exec`, disabled by default.
- `e2b_cloud`: future production candidate, enabled only with explicit
  credentials and `NBA_ENABLE_PYTHON_CODE_SANDBOX=1`.
- `vercel_sandbox`: future alternative if a TypeScript broker/service is
  introduced.

Slice 18 should:

- add the interface and backend selection;
- add a mocked external backend for deterministic tests;
- keep real vendor calls behind env gates;
- fail closed when credentials are absent;
- continue routing code mode only through `python_analysis.run`;
- never expose raw SQL, DB handles, credentials, or raw filesystem paths to the
  sandbox.

## Out Of Scope

- Adding E2B or Vercel SDK dependencies now.
- Calling vendor APIs.
- Requiring credentials.
- Making `python_code` default-on.
- Adding model-visible `raw_python`, `python_code`, `raw_sql`, or
  `duckdb.execute` tools.
- Letting sandbox code query DuckDB, inspect the warehouse, or author SQL.

## Open Questions Before Production Enablement

- Which account owns sandbox vendor billing?
- What usage budget and concurrency limit are acceptable?
- Should code mode be internal-only, beta-user gated, or public?
- What production deployment region/latency targets matter?
- Should sandbox traces be retained, and for how long?
