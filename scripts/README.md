# Scripts

Local developer helper scripts live here.

Examples:

- bootstrapping local services
- fixture loading
- running end-to-end demo flows
- evaluation helpers

## Web helpers

Run the web app through optional Portless dev routing:

```bash
scripts/run_web_portless.sh
```

This opens the app at:

```text
https://nba-analyst.localhost
```

If Portless is not installed, use the plain Uvicorn command from `apps/web/README.md`.
