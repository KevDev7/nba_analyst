# Python Analysis

`python_analysis.run` is a derived-analysis tool. It is not allowed to retrieve product data directly, and it is never a SQL authoring boundary.

## Default Path

Use controlled operations whenever they fit:

- `join_and_delta`
- `rank_extremes`
- `correlation`
- `percent_change`
- `zscore_outliers`
- chart operations

Controlled operations remain preferred because their behavior is typed, deterministic, and easier to evaluate.

## Gated Code Mode

`python_code` is a local/beta-only sandbox prototype for custom analysis over approved tables. It is disabled unless:

```text
NBA_ENABLE_PYTHON_CODE_SANDBOX=1
```

Requirements:

- input tables must be explicitly supplied to the request;
- code can reference only declared input table ids;
- output tables must be declared up front;
- output rows must match declared schemas;
- row limits and timeouts are enforced;
- stdout/stderr are captured;
- provenance records `code_hash`, parent tables, output tables, runtime id, and timeout state.

The sandbox receives serialized table data only. It does not receive:

- raw SQL;
- a DuckDB connection;
- database clients;
- direct warehouse/table access;
- ontology internals;
- credentials;
- environment variables;
- arbitrary filesystem paths.

The local runner uses a subprocess plus macOS `sandbox-exec` when available. Provenance records `sandbox_backend: "macos_sandbox_exec"`, `sandbox_status: "local_beta_only"`, and `production_ready: false`.

The Python layer also rejects forbidden imports and calls, including `duckdb`, `sqlite3`, `sqlalchemy`, `socket`, `requests`, `urllib`, `os`, `subprocess`, `pathlib`, `open`, `eval`, `exec`, and `compile`.

Code mode must not write SQL strings, repair SQL, transform SQL, or inspect database schemas. Haskell remains the only SQL author; code mode may only compute over approved tables that were already retrieved through `semantic_query.plan_execute`.

Code-mode outputs are evidence tables/findings, not final answer prose. Final user-facing synthesis must still use deterministic synthesis or the grounded answer composer with evidence references.

## Production Requirements

Do not treat the local `python_code` runner as a production sandbox. A production-ready backend should provide:

- Linux/container or microVM isolation;
- no network namespace by default;
- no host filesystem access except an ephemeral scratch directory;
- CPU and hard memory limits;
- process-tree kill on timeout;
- clean environment without secrets;
- dependency allowlist and runtime image/hash provenance;
- backend-specific adversarial tests in CI.

## Production Backend Decision

See [SANDBOX_VENDOR_DECISION.md](SANDBOX_VENDOR_DECISION.md) for the Slice 17 production sandbox recommendation and the requirements for a future `SandboxBackend` implementation.

## Sandbox Backends

Code mode now runs through a pluggable backend interface selected by:

```text
NBA_PYTHON_CODE_SANDBOX_BACKEND=local_beta|e2b_cloud
```

Supported backends:

- `local_beta`: current macOS `sandbox-exec` backend. It remains disabled by
  default and is not production-ready.
- `e2b_cloud`: E2B cloud sandbox backend. It is disabled by default, requires
  `NBA_ENABLE_PYTHON_CODE_SANDBOX=1` and `E2B_API_KEY`, creates sandboxes with
  internet disabled, and fails closed if credentials or the SDK are absent.
- `mock_e2b`: deterministic test backend only. It performs no real code
  execution and exists to test backend plumbing without credentials.

All backends return the same provenance shape: backend id, runtime id, sandbox
status, production readiness, code hash, parent/output table ids, stdout/stderr,
execution duration, and timeout state.
