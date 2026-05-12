# Python Analysis

`python_analysis.run` is a derived-analysis tool. It is not allowed to retrieve product data directly.

## Default Path

Use controlled operations whenever they fit:

- `join_and_delta`
- `rank_extremes`
- chart operations

Controlled operations remain preferred because their behavior is typed, deterministic, and easier to evaluate.

## Gated Code Mode

`python_code` is a sandbox prototype for custom analysis over approved tables. It is disabled unless:

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
- ontology internals;
- credentials;
- environment variables;
- arbitrary filesystem paths.

The local runner uses a subprocess plus macOS `sandbox-exec` when available. The Python layer also rejects forbidden imports and calls, including `duckdb`, `sqlite3`, `socket`, `requests`, `urllib`, `os`, `subprocess`, `pathlib`, `open`, `eval`, `exec`, and `compile`.

Code-mode outputs are evidence tables/findings, not final answer prose. Final user-facing synthesis must still use deterministic synthesis or the grounded answer composer with evidence references.
