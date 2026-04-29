# NBA Analyst

`nba_analyst` is a fresh repo for a new NBA analytics agent built around the same core service shape we inferred from TextQL's public writing, while explicitly ignoring the out-of-scope enterprise extras.

## Goal

The product goal is narrow and clear:

- a user asks an open-ended analytics question
- the system maps that question into a semantic model
- the system plans and executes a real investigation
- the system runs SQL and Python analysis iteratively
- the system returns an analytical answer, not just a query

## Repo Layout

This repo is shaped around five main parts:

1. `services/ontology-hs`
Haskell semantic core for:
- ontology definitions
- typed query IR / DSL
- reference resolution
- validation
- compilation from semantic intent to executable query plan

2. `services/runtime-py`
Python analysis runtime for:
- query execution
- intermediate artifacts
- dataframe/statistical analysis
- iteration over results

3. `services/orchestrator`
Thin orchestration layer for:
- receiving user questions
- calling the semantic core
- invoking the analysis runtime
- returning final answers

The current local product path uses `apps/assistant/pipeline.py` as the shared
orchestration boundary for CLI and web. `services/orchestrator` remains a
placeholder for a future service split.

4. `apps`

Product adapters:
- `apps/cli`
  - terminal surface over the shared assistant pipeline
- `apps/web`
  - localhost FastAPI + simple HTML/JS surface over the same pipeline

5. `contracts`
Shared contract surface for:
- semantic/query IR
- plan/result payload shapes
- answer/report payloads

Additional repo structure:

- `fixtures`
  - local data snapshots, example ontology configs, sample inputs
- `evals`
  - question sets, expected behaviors, and benchmark scaffolding
- `scripts`
  - local developer helpers

## Intentionally Out Of Scope

Not part of the first build:

- extreme table-count scale
- broad connector ecosystem
- Slack / Playbooks / Dashboards
- healthcare-specific vertical logic
- large infra/platform sophistication
- multimodal dashboard recreation

## Current Local Product Path

The current one-step assistant supports six query families:

- ranking / top-N
- aggregation
- filtering / joining
- trend
- comparison
- object rows

It uses:

- a generated NBA semantic ontology fixture
- Gemini for a loose semantic draft
- a Haskell semantic core for query modeling, grounding, validation, and plan compilation
- a Python runtime over DuckDB
- grounded answer synthesis and formatting

Run it with:

```bash
python3 apps/cli/main.py "Show me the top 10 players by points over the last 10 games" --debug
```

Run the localhost web app with:

```bash
uvicorn apps.web.server:app --reload --host 127.0.0.1 --port 8000
```

Or use the optional Portless helper for a stable local URL:

```bash
scripts/run_web_portless.sh
```

Then open:

```text
https://nba-analyst.localhost
```

Run the assistant test suite with:

```bash
python3 -m pytest tests -q
```

Run a smaller focused smoke test with:

```bash
python3 -m unittest tests.test_web_api tests.test_cli_pipeline tests.test_semantic_interpreter tests.test_semantic_draft_grounding
```

Note: full repository-wide `pytest` discovery also collects optional ingestion
and Athena pipeline tests. Those may require extra packages such as `nba_api`
or `pbpstats`; use `python3 -m pytest tests -q` for the current assistant suite.
