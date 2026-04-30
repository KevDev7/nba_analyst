# CLI App

This is the terminal product surface for `nba_analyst`.

Why CLI first:

- prove the core analysis loop before building UI
- keep iteration fast
- make evaluation and debugging straightforward

Live flow:

`question -> Gemini semantic draft -> Haskell grounding/planning -> Python runtime -> answer synthesis -> terminal output`

The CLI owns only terminal input/output. Shared semantic interpretation lives in
`apps/assistant/semantic`, and the shared orchestration path lives in
`apps/assistant/pipeline.py`.

Current scope:

- one user question
- one grounded execution plan
- one terminal answer
- six supported query families: ranking, aggregation, filtering/find,
  trend, comparison, and object rows
