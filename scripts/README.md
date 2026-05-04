# Scripts

Local developer helper scripts live here.

Examples:

- bootstrapping local services
- fixture loading
- running end-to-end demo flows
- evaluation helpers

## API helpers

Run the assistant API through optional Portless dev routing:

```bash
scripts/run_api_portless.sh
```

This exposes the API at:

```text
https://nba-insight-api.localhost
```

If Portless is not installed, use the plain Uvicorn command from `apps/web/README.md`.

## UI helpers

Run the SvelteKit browser UI through optional Portless dev routing:

```bash
scripts/run_web_ui_portless.sh
```

This exposes the UI at:

```text
https://nba-insight-ui.localhost
```

The browser UI is not served by FastAPI. It proxies `/api/*` to the FastAPI API during development.
