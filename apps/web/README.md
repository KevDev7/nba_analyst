# Assistant API

FastAPI API surface for `nba_analyst`.

Run it with:

```bash
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000
```

The service is intentionally API-only:

- `POST /api/chat` calls the shared assistant pipeline.
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
