# Software Future Work

This file tracks software-side follow-ups that are not data-pipeline work.

## LLM semantic draft reliability

Observed during Wave 4 CLI testing:

- The same natural-language question can produce different Gemini responses
  across calls.
- For `Find games where the Lakers or Warriors scored over 120 points`, one
  run returned malformed JSON before Haskell saw the draft.
- A later run with the same question returned valid JSON, and the semantic
  predicate path worked end to end.

Why this matters:

- This is not an ontology/planner capability gap.
- It is an LLM transport / structured-output reliability issue.
- User-facing behavior should not randomly fail before the semantic contract
  gets a chance to validate and ground the request.

Later fix options:

- Configure the LLM call for stricter JSON or schema-constrained output when
  available.
- Add an automatic retry when JSON parsing fails.
- Add a JSON repair pass that only repairs syntax and never changes semantic
  meaning.
- Keep fallback-model support for provider instability, but do not treat fallback
  as a substitute for schema/parse reliability.
