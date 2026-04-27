# Web App

Localhost web surface for `nba_analyst`.

Run it with:

```bash
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

Optional Portless dev URL:

```bash
scripts/run_web_portless.sh
```

Then open:

```text
https://nba-analyst.localhost
```

Portless is only a local dev convenience. The web app still works without it.

The web app is intentionally thin:

- `POST /api/chat` calls the shared assistant pipeline
- the browser page renders one answer or one clear error
- debug mode shows the same major pipeline handoffs as CLI `--debug`
- semantic interpretation, ontology grounding, SQL planning, runtime execution, and answer synthesis stay outside the web layer
