# Assistant API

FastAPI API surface for `nba_analyst`.

Run it with:

```bash
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/healthz
```

The service is intentionally API-only:

- `POST /api/chat` calls the shared assistant pipeline.
- `GET /healthz` checks the deployed planner binary and committed DuckDB snapshot.
- `GET /` does not serve a browser UI.
- Semantic interpretation, ontology grounding, SQL planning, runtime execution, and answer synthesis stay outside the web layer.

The structured browser UI lives in `apps/web-ui` and runs as a separate SvelteKit dev server that proxies `/api/*` to this API.

Optional Portless API URL:

```bash
scripts/run_api_portless.sh
```

That exposes the API at:

```text
https://nba-insight-api.localhost
```

## Render backend deployment

The backend Docker image builds the Haskell ontology planner once, installs it
at `/app/bin/ontology-hs`, and runs the API with:

```bash
uvicorn apps.web.server:app --host 0.0.0.0 --port ${PORT:-10000}
```

Render can use the root `render.yaml` blueprint. It prompts for
`GEMINI_API_KEY` because the blueprint marks it with `sync: false`.

The deployed service sets:

```text
NBA_ONTOLOGY_PLANNER_BIN=/app/bin/ontology-hs
NBA_DISABLE_SNAPSHOT_REBUILD=1
NBA_ALLOWED_ORIGINS=https://nba-analyst-ui.onrender.com
NBA_ENABLE_PUBLIC_DEBUG=0
NBA_MAX_QUESTION_CHARS=250
```

That means the deployed app uses the committed
`fixtures/duckdb/gold_slice.duckdb` snapshot and fails clearly if the snapshot
is missing or stale instead of trying to rebuild from Athena.

`NBA_ALLOWED_ORIGINS` is a comma-separated list of browser origins allowed to
call the API through CORS. Local dev normally does not need it because Vite
proxies `/api/*` to the API server.

`POST /api/chat` ignores request-body `debug: true` unless
`NBA_ENABLE_PUBLIC_DEBUG=1` is set. Keep this off for public deployments because
debug payloads include internal semantic drafts, execution plans, SQL, and
grounding traces.

`POST /api/chat` also rejects public web questions above
`NBA_MAX_QUESTION_CHARS` after trimming whitespace and before calling the LLM,
planner, or runtime. The beta default is `250`.
