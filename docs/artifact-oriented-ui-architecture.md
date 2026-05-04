# Artifact-Oriented UI Architecture

This note captures a direction for the next frontend/runtime boundary.

The product should not permanently depend on this fixed order:

```text
SQL result -> answer text -> markdown table -> UI table
```

Instead, execution should produce structured artifacts that different renderers
can consume:

```text
user question
-> semantic planning
-> execution/tool calls
-> artifacts/results
-> presentation layer renders artifacts
```

Examples of future artifact kinds:

- `text`: summaries, assumptions, caveats, interpretation notes
- `table`: columns, rows, column types, row counts, source metadata
- `chart`: chart spec, source table reference, generated image or UI config
- `file`: downloadable generated artifact
- `debug`: plan, SQL, traces, tool logs

The important boundary:

- execution creates results and artifacts
- synthesis explains results
- presentation renders artifacts
- CLI and web can render the same artifacts differently
- future tools, such as a Python sandbox, can add artifacts without forcing the
  whole pipeline into one hardcoded order

This keeps the table component, ASCII answer, chart generation, and later
multi-step agent/tool orchestration modular instead of tightly coupled.
