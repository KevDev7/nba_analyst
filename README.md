# NBA Insights

NBA Insights is a beta NBA analytics assistant that turns natural-language basketball questions into grounded answers, tables, and charts.

The system uses an ontology-backed semantic layer to map flexible user questions onto supported NBA entities, metrics, dimensions, filters, and time windows, then executes the resulting analysis against a local DuckDB snapshot.

## What It Can Answer

NBA Insights is built for grounded basketball analysis, not general sports chat. The current product supports:

- **Rankings:** top, bottom, best, worst, most, fewest, highest, and lowest players or teams.
- **Aggregates:** grouped summaries across players, teams, games, seasons, and basketball context.
- **Trends:** daily, weekly, monthly, yearly, and season-by-season movement.
- **Comparisons:** two or more named players or teams across one metric, many metrics, or time buckets.
- **Custom stat tables:** player or team rows with selected stats and natural limits.
- **Find queries:** game logs, player game logs, team game logs, display columns, sorting, and matching rows.
- **Context filters:** home, road, starter, bench, opponent, conference, regular season, playoffs, teams, and players.
- **Calculated-result filters:** questions like "teams with net rating above 5" or "players averaging at least 8 assists."

## Example Questions

```text
Who are the best defensive teams this season?
Which players have the fewest turnovers over the last 10 games?
Show players averaging at least 8 assists over the last 10 games.
Compare Brunson and Tatum by points, assists, and rebounds over the last 10 games.
Compare Lakers and Warriors rebounding by month over the past year.
Find Celtics games with more than 15 threes and fewer than 12 turnovers.
Rank teams by net rating on the road over the last 10 games.
Show teams and their steals, blocks, and rebounds in the 2025-26 regular season.
```

## Data Coverage

The committed local snapshot currently covers NBA data from the 2020-21 season through the 2025-26 season.

Supported data surfaces include:

- players, teams, arenas, and games
- player game logs and team game logs
- player season, player-season-team, and team season summaries
- box score, shooting, scoring-detail, rebounding, fouling, possession, and advanced efficiency stats where present in the ontology

Game-level stats are the lowest supported detail today. Possession-by-possession, lineup, on/off, clutch, shot-location, and play-by-play analysis are not first-class product capabilities yet.

## Architecture

The working product path is:

```text
User question
  -> apps/assistant semantic interpreter
  -> services/ontology-hs semantic planner
  -> services/runtime-py DuckDB runtime
  -> answer synthesis
  -> CLI, FastAPI, or SvelteKit UI
```

Core pieces:

- `apps/assistant`: shared Python assistant pipeline used by CLI and web.
- `apps/cli`: terminal adapter for one-question assistant runs.
- `apps/web`: FastAPI API surface over the shared assistant pipeline.
- `apps/web-ui`: SvelteKit structured artifact frontend.
- `services/ontology-hs`: Haskell ontology loader, semantic draft grounding, typed query IR, validation, and SQL plan compilation.
- `services/runtime-py`: Python execution runtime, answer packaging, synthesis models, and artifact support.
- `fixtures`: committed ontology and DuckDB snapshot fixtures.
- `evals`: question bank and evaluation scaffolding.
- `contracts`: human-readable contract notes for query, execution, and answer payloads.
- `scripts`: local development and snapshot helpers.

`services/orchestrator` is currently a placeholder for a future service split. The active Python orchestration seam lives in `apps/assistant/orchestrator.py`, with `apps/assistant/pipeline.py` kept as the stable CLI/web compatibility entrypoint.

The first governed assistant tools live under `apps/assistant/tools`:

- `semantic_query.plan_execute` wraps the current ontology-grounded query path.
- `ontology_catalog.inspect` exposes ontology and snapshot coverage for future orchestration.
- `artifact_renderer.render` wraps text/table/chart artifact generation without changing the artifact JSON contract.
- `python_analysis.run` runs controlled derived analysis over approved result tables.

The first governed multi-call route supports explicit season-over-season period deltas by calling the semantic query tool twice, computing the delta with controlled Python analysis, and rendering the derived table through the artifact renderer.

## Requirements

Local development expects:

- Python 3.12 or compatible Python 3
- Haskell Cabal/GHC for local ontology planner runs
- Node.js and npm for the SvelteKit UI
- a Gemini API key for semantic interpretation

Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
npm ci --prefix apps/web-ui
```

Create local environment config from the example:

```bash
cp .env.example .env
```

Then set at least:

```text
GEMINI_API_KEY=...
```

Keep real secrets out of git.

## Run Locally

Run a CLI question:

```bash
python3 apps/cli/main.py "Show me the top 10 players by points over the last 10 games"
```

Run the FastAPI assistant API:

```bash
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000
```

Check API health:

```bash
curl http://127.0.0.1:8000/healthz
```

Run the SvelteKit frontend separately:

```bash
npm --prefix apps/web-ui run dev
```

During local frontend development, `/api/*` requests are proxied to `http://127.0.0.1:8000`.

Optional Portless helpers:

```bash
scripts/run_api_portless.sh      # https://nba-insight-api.localhost
scripts/run_web_ui_portless.sh   # https://nba-insight-ui.localhost
```

## Deploy To Render

The root `render.yaml` defines two Render services:

- `nba-analyst-api`: Docker web service for the FastAPI backend.
- `nba-insight-mdpl`: static site for the SvelteKit frontend.

The backend Docker image builds the Haskell planner once, installs it at `/app/bin/ontology-hs`, disables runtime Athena snapshot rebuilds, and starts:

```bash
uvicorn apps.web.server:app --host 0.0.0.0 --port ${PORT:-10000}
```

The frontend builds with:

```bash
npm ci --prefix apps/web-ui && npm --prefix apps/web-ui run build
```

and publishes:

```text
apps/web-ui/build
```

Render prompts for `GEMINI_API_KEY` because the blueprint marks it with `sync: false`.

## Environment Variables

Backend:

```text
GEMINI_API_KEY                  # required secret for semantic interpretation
LLM_INTERPRETER_PROVIDER        # usually google
GEMINI_MODEL                    # primary Gemini model
GEMINI_FALLBACK_MODELS          # comma-separated fallback models
NBA_ONTOLOGY_PLANNER_BIN        # use /app/bin/ontology-hs in Render
NBA_DISABLE_SNAPSHOT_REBUILD    # set 1 in deployed environments
NBA_ALLOWED_ORIGINS             # comma-separated browser origins for CORS
NBA_ENABLE_PUBLIC_DEBUG         # keep 0 publicly
NBA_MAX_QUESTION_CHARS          # beta default: 250
```

Frontend:

```text
PUBLIC_API_BASE_URL             # deployed backend API URL
PUBLIC_MAX_QUESTION_CHARS       # composer maxlength; backend still enforces the real limit
```

## Safety Defaults

The public beta deployment is intentionally conservative:

- `GEMINI_API_KEY` is backend-only and should never be bundled into the frontend.
- `NBA_ENABLE_PUBLIC_DEBUG=0` prevents users from requesting semantic drafts, SQL, execution plans, and grounding traces.
- `NBA_MAX_QUESTION_CHARS=250` rejects oversized prompts before LLM, planner, or runtime work.
- `NBA_ALLOWED_ORIGINS` restricts browser CORS access to the deployed UI origin.
- `NBA_DISABLE_SNAPSHOT_REBUILD=1` makes Render use the committed DuckDB snapshot instead of trying to rebuild from Athena.

## Tests

Run the assistant suite:

```bash
python3 -m pytest tests -q
```

Run a focused smoke set:

```bash
python3 -m unittest tests.test_web_api tests.test_cli_pipeline tests.test_semantic_interpreter tests.test_semantic_draft_grounding
```

Run frontend checks:

```bash
npm --prefix apps/web-ui run check
npm --prefix apps/web-ui run build
```

Note: repository-wide `pytest` discovery may collect optional ingestion and Athena pipeline tests that need extra packages such as `nba_api` or `pbpstats`. Use `python3 -m pytest tests -q` for the current assistant suite.

## Known Limits

The product is intentionally grounded in the ontology and committed data snapshot. A question should fail when the ontology, data, or supported query shape cannot represent it.

Current known gaps include:

- possession-by-possession, lineup, on/off, clutch, and shot-location analysis
- first-class composite metrics like PRA, PR, RA, and stocks
- free-form "all information about this entity" object expansion
- comparison result filters
- trends over "last N games" instead of calendar-style time buckets
- live data refresh during deployed requests

## More Detail

- Backend API details: `apps/web/README.md`
- Frontend UI details: `apps/web-ui/README.md`
- Semantic graph notes: `docs/supported-ontology-graph.md`
- Question bank: `evals/question_bank.json`
