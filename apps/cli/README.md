# CLI App

This is the terminal product surface for `nba_analyst`.

Why CLI first:

- prove the core analysis loop before building UI
- keep iteration fast
- make evaluation and debugging straightforward

Live flow:

`question -> Gemini semantic draft -> Haskell grounding/planning -> Python runtime -> answer synthesis -> terminal output`

Current scope:

- one user question
- one grounded execution plan
- one terminal answer
- six supported query families: ranking, aggregation, filtering/find,
  trend, comparison, and object rows
