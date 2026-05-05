# Web UI

SvelteKit + TypeScript frontend for the structured artifact UI.

This app is a presentation layer over the existing FastAPI assistant API. It does
not interpret user questions, build SQL, or bypass ontology grounding.

## Run Locally

Start the assistant API:

```bash
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000
```

Start the SvelteKit frontend:

```bash
npm --prefix apps/web-ui run dev
```

Open the SvelteKit dev URL printed by Vite.

During development, `/api/*` requests are proxied to `http://127.0.0.1:8000`.
Set `NBA_INSIGHT_API_URL` if the local API is running somewhere else.

Optional Portless dev URL:

```bash
scripts/run_web_ui_portless.sh
```

Then open:

```text
https://nba-insight-ui.localhost
```

Portless only wraps the SvelteKit UI in this setup. The FastAPI assistant API
still runs on `127.0.0.1:8000`, and SvelteKit proxies `/api/*` to it.

## Render static-site deployment

The frontend deploys as a Render static site through the root `render.yaml`
blueprint. Render builds it with:

```bash
npm ci --prefix apps/web-ui && npm --prefix apps/web-ui run build
```

The publish directory is:

```text
apps/web-ui/build
```

In deployed builds, set:

```text
PUBLIC_API_BASE_URL=https://nba-analyst-api.onrender.com
PUBLIC_MAX_QUESTION_CHARS=250
```

Without `PUBLIC_API_BASE_URL`, the browser keeps using `/api/chat`, which is
what local Vite proxy development expects.

`PUBLIC_MAX_QUESTION_CHARS` only controls the browser composer `maxlength`.
The FastAPI backend still enforces the authoritative `NBA_MAX_QUESTION_CHARS`
limit.

## Current Artifact Behavior

- Submit one natural-language analytics question.
- Show loading, success, and error states.
- Render structured `text` artifacts.
- Render structured `table` artifacts with TanStack Table Core.
- Render structured Vega-Lite `chart` artifacts with `vega-embed`.

Chart rendering is presentation-only. The frontend does not decide when a chart
should exist; it only renders chart artifacts returned by the assistant API.
