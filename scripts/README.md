# Scripts

Local developer helper scripts live here.

Examples:

- bootstrapping local services
- fixture loading
- running end-to-end demo flows
- evaluation helpers

## Web helpers

Run the Scope 2 FastAPI static web app through optional Portless dev routing:

```bash
scripts/run_web_portless.sh
```

This opens the app at:

```text
https://nba-analyst.localhost
```

If Portless is not installed, use the plain Uvicorn command from `apps/web/README.md`.

Run the Scope 3 SvelteKit UI through optional Portless dev routing:

```bash
scripts/run_web_ui_portless.sh
```

This opens the app at:

```text
https://nba-analyst-ui.localhost
```

Start the FastAPI assistant API separately first:

```bash
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000
```
