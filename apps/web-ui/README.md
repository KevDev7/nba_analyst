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

Optional Portless dev URL:

```bash
scripts/run_web_ui_portless.sh
```

Then open:

```text
https://nba-analyst-ui.localhost
```

Portless only wraps the SvelteKit UI in this setup. The FastAPI assistant API
still runs on `127.0.0.1:8000`, and SvelteKit proxies `/api/*` to it.

## Current Artifact Behavior

- Submit one natural-language analytics question.
- Show loading, success, and error states.
- Render structured `text` artifacts.
- Render structured `table` artifacts with TanStack Table Core.
- Render structured Vega-Lite `chart` artifacts with `vega-embed`.

Chart rendering is presentation-only. The frontend does not decide when a chart
should exist; it only renders chart artifacts returned by the assistant API.
