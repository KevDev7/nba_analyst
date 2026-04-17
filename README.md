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

This repo is being shaped around four main parts:

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

4. `contracts`
Shared contract surface for:
- semantic/query IR
- plan/result payload shapes
- answer/report payloads

Additional repo structure:

- `apps/cli`
  - first product surface for proving the core loop
- `apps/web`
  - optional later UI surface once the core works
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

## Vertical Slice 1

The first working slice supports:

- `Show me the top 10 players by points over the last 10 games`

It uses:

- a minimal NBA ontology fixture
- a Haskell semantic core for query modeling and grounded planning
- a Python runtime over DuckDB
- templated answer synthesis

Run it with:

```bash
python3 apps/cli/main.py "Show me the top 10 players by points over the last 10 games" --debug
```

Run the slice-1 tests with:

```bash
python3 -m unittest tests.test_slice_one
```
