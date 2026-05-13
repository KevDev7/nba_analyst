# Evals

This folder is for evaluation assets and harnesses.

Examples:

- gold-standard questions
- expected answer characteristics
- semantic-mapping checks
- query-plan checks
- end-to-end answer quality tests
- persistent question banks for regression memory

The core product should be measured here before a full web UI is prioritized.

## Orchestrator Trace Evals

`orchestrator_trace_eval_bank.json` is a deterministic guardrail bank for governed orchestration traces. It covers:

- simple semantic-query fast path;
- governed multi-step period deltas;
- unsupported ontology surfaces;
- adversarial raw-SQL requests;
- artifact and claim/evidence expectations;
- sandbox policy shape.

The harness intentionally avoids live provider calls. It asserts tool sequences, forbidden tool names, raw SQL/private-debug redaction, artifact kinds, and claim/evidence coverage where applicable.
