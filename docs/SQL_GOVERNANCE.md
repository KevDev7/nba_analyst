# SQL Governance

## Permanent Invariant

Haskell is the only SQL author for product data retrieval.

The runtime executes Haskell-generated SQL safely, but there is no product path
for model-authored, user-authored, Python-authored, sandbox-authored, repaired,
or transformed SQL.

This is not a temporary implementation choice. It is part of the product
contract: users and models ask in semantic basketball terms; Haskell grounds the
request against the ontology and compiles retrieval SQL; Python analyzes only
approved result tables after retrieval.

## Allowed

- Haskell ontology planner compiles SQL from validated semantic drafts or query
  IR.
- Runtime executes Haskell-generated SQL against DuckDB read-only.
- Runtime records execution metadata:
  - `sql_hash`
  - `sql_redacted: true`
  - execution duration
  - returned row count
  - requested row limit
  - row-limit enforcement status
  - truncation status
- Developer-only private debug may include raw execution plans only when all
  private-debug gates are enabled.

## Permanently Forbidden

- model-authored SQL;
- user-authored SQL execution;
- Python-authored SQL;
- sandbox-authored SQL;
- SQL repair or SQL transformation tools;
- model-visible SQL snippets;
- public raw SQL exposure;
- direct DuckDB/database/warehouse access from the model, Python analysis, or
  sandbox code;
- public/model-visible tools named `raw_sql`, `governed_sql`, `sql.execute`, or
  `duckdb.execute`.

## Why Runtime SQL Governance Still Exists

Runtime governance is execution safety for trusted Haskell output, not
permission for new SQL authors. It provides defense-in-depth and provenance:

- read-only DuckDB connection;
- defensive single-statement guard;
- row caps and truncation metadata;
- timeout metadata where available;
- SQL hashes for reproducibility;
- redacted public/model-visible traces.

## If A Future Feature Seems To Need SQL

Do not add a SQL tool. Add or extend one of these instead:

- ontology metric/dimension/filter/link definitions;
- Haskell semantic grounding or SQL compilation;
- a governed semantic-query plan shape;
- a controlled `python_analysis.run` operation over already retrieved tables.

If the ontology cannot express the data surface, the assistant should return a
grounded limitation or ask for the nearest supported semantic request.
