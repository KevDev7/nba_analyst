# Orchestrator

This service is intentionally thin.

Primary responsibilities:

- accept user questions
- call the ontology service
- invoke the analysis runtime
- assemble the final answer payload

The goal is to keep product/API wiring separate from the semantic core and runtime logic.
