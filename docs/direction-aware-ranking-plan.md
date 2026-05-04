# Direction-Aware Ranking Plan

## Product Goal

Users should be able to ask ranking questions with quality language such as
`best`, `worst`, `top`, `bottom`, `highest`, `lowest`, `most`, and `fewest`
without the assistant returning an objectively wrong sort direction.

Examples this should support:

- `best defensive teams this season`
- `worst defensive teams this season`
- `fewest turnovers by players over the last 10 games`
- `most turnovers by players over the last 10 games`
- `top teams by net rating this season`
- `bottom teams by net rating this season`
- `best teams by opponent field goal percentage`

The important part is that this must be ontology-grounded. The model can
preserve the user's intent, but the semantic layer should decide the final
ranking direction using metric semantics from the ontology contract.

## Why This Exists

Ranking direction is currently resolved before the requested measure is grounded
to an ontology metric. That means the planner cannot know whether a metric is
better when higher or lower.

For example:

```text
best teams by defensive rating
```

should sort defensive rating ascending, because lower defensive rating is
better. But the current sort resolver only sees broad sort words and maps them
directly to `ASC` or `DESC` without metric context.

This is not an aliasing problem. `defensive rating` can ground correctly and
still sort incorrectly if the system does not know the metric's ranking
polarity.

## Product Principle

The ontology contract should remain the safety boundary.

The system should not add phrase-specific corridors such as:

```text
if phrase contains "best defense", force defensive_rating ASC
```

That would make the assistant brittle and would not generalize to future
metrics.

Instead, the ontology should describe the metric:

```yaml
ranking_polarity: lower_is_better
```

Then rank intent can be resolved generically:

```text
best + lower_is_better -> ASC
worst + lower_is_better -> DESC
best + higher_is_better -> DESC
worst + higher_is_better -> ASC
```

## Target Conceptual Model

Direction-aware ranking should separate three concepts:

```text
rank intent = what the user asked for
metric polarity = what the ontology knows about the metric
SQL direction = how to execute the rank
```

Example:

```text
Question: best defensive teams
Rank intent: best
Metric: defensive_rating
Metric polarity: lower_is_better
SQL direction: ASC
Presentation: Best teams by defensive rating
```

Another example:

```text
Question: highest defensive rating
Rank intent: highest
Metric: defensive_rating
Metric polarity: lower_is_better
SQL direction: DESC
Presentation: Teams with highest defensive rating
```

The second query is intentionally different. `highest` is a quantity intent,
not a quality intent. If a user asks for the highest defensive rating, the
assistant should not reinterpret that as best defense.

## Slice 1: Ontology Metric Ranking Semantics

Purpose:

Add ranking polarity to executable ontology metrics so the semantic layer knows
whether higher or lower values are better.

Implementation:

- Add a metric polarity type in
  `services/ontology-hs/src/OntologyLayer/Types.hs`.
- Add a field to `MetricDef`, likely:

```haskell
ranking_polarity :: MetricRankingPolarity
```

- Supported values:

```text
higher_is_better
lower_is_better
neutral
```

- Parse the new field from `semantic-gold.yaml`.
- Validate the field in
  `services/ontology-hs/src/OntologyLayer/Validation.hs`.
- Generate the field from `scripts/generate_semantic_ontology.py`.
- Regenerate `fixtures/ontology/semantic-gold.yaml`.

Initial polarity rules:

- `higher_is_better`
  - `net_rating`
  - `offensive_rating`
  - `wins`
  - `win_percentage`
  - `points`
  - `assists`
  - `rebounds`
  - `offensive_rebounds`
  - `defensive_rebounds`
  - `steals`
  - `blocks`
  - `field_goals_percentage`
  - `two_pointers_percentage`
  - `three_pointers_percentage`
  - `free_throws_percentage`
  - `effective_field_goal_percentage`
  - `true_shooting_percentage`
  - `assist_to_turnover_ratio`
  - `steal_percentage`
  - `assist_percentage`
  - `offensive_rebound_percentage`
  - `defensive_rebound_percentage`
  - `rebound_percentage`
  - `fouls_drawn`

- `lower_is_better`
  - `defensive_rating`
  - `losses`
  - `turnovers`
  - `personal_fouls_committed`
  - `technical_fouls_committed`
  - `offensive_fouls_committed`
  - opponent scoring metrics, such as `opponent_points`
  - opponent shooting efficiency metrics, such as
    `opponent_field_goals_percentage`
  - opponent made-shot metrics, such as `opponent_three_pointers_made`
  - opponent rebounding metrics where allowed production is bad, such as
    `opponent_offensive_rebounds`

- `neutral`
  - `games_played`
  - `games_started`
  - `minutes`
  - `possessions`
  - `pace`
  - shot attempts
  - other volume/context metrics where higher is not inherently better

Important nuance:

Do not blindly mark every `opponent_*` metric as `lower_is_better`.
`opponent_turnovers` is usually `higher_is_better`. Some opponent foul metrics
may be neutral or context-dependent. The generator should use explicit families
and overrides, not only string prefixes.

Done when:

- Every executable metric in `semantic-gold.yaml` has a ranking polarity.
- Ontology loading fails on missing or invalid polarity values.
- Tests prove known metrics carry expected polarity.
- Existing metric grounding and SQL compilation behavior remains unchanged.

Suggested tests:

- `defensive_rating` and `average_defensive_rating` are `lower_is_better`.
- `net_rating` and `average_net_rating` are `higher_is_better`.
- `turnovers`, `turnovers_per_game`, and `total_turnovers` are
  `lower_is_better`.
- `opponent_field_goals_percentage` is `lower_is_better`.
- `opponent_turnovers` is not accidentally treated as `lower_is_better`.
- `pace` and `possessions` are `neutral`.

## Slice 2: Rank Intent Resolution After Metric Grounding

Purpose:

Capture the user's ranking intent separately from raw sort direction, then
resolve final `ASC` or `DESC` only after the metric has been grounded to an
ontology `MetricDef`.

Implementation:

- Add `rank_intent` to the Python semantic draft model in
  `apps/assistant/semantic/interpreter.py`.
- Add `rankIntent` to Haskell `SemanticDraft` in
  `services/ontology-hs/src/QueryModel/SemanticDraft/Types.hs`.
- Update the interpreter prompt so rank questions preserve intent:

```json
{
  "rank_intent": "best"
}
```

instead of forcing every quality phrase into `sort: "desc"` or `sort: "asc"`.

- Keep `sort` for literal direction language only:
  - `ascending`
  - `descending`
  - `asc`
  - `desc`

- Move rank order resolution in
  `services/ontology-hs/src/QueryModel/SemanticConstruction/Build/Rank.hs`.
  The current flow resolves sort before grounding. The new flow should be:

```text
parse draft
resolve subject
resolve dimensions
ground metric
read metric ranking polarity
resolve rank intent + polarity into order
build query IR
```

- Replace or extend `requireRankingSort` with a metric-aware function, likely:

```haskell
resolveRankingOrder ::
  SemanticDraft ->
  MetricDef ->
  Either Text (QI.MetricName -> QI.Order)
```

Resolution table:

```text
highest / most        -> DESC
lowest / fewest/least -> ASC

best / top / leaders:
  higher_is_better -> DESC
  lower_is_better  -> ASC
  neutral          -> DESC

worst / bottom:
  higher_is_better -> ASC
  lower_is_better  -> DESC
  neutral          -> ASC

explicit desc / descending -> DESC
explicit asc / ascending   -> ASC
missing intent             -> existing default DESC
```

Why `highest` and `best` differ:

```text
highest defensive rating -> DESC
best defensive rating    -> ASC
```

That distinction is what makes this semantic instead of a fragile keyword
hack.

Done when:

- Direction is resolved after the metric is grounded.
- `best` and `worst` depend on metric polarity.
- `highest`, `lowest`, `most`, and `fewest` preserve quantity semantics.
- Existing `top N by points` behavior still sorts descending.
- Existing `bottom N by points` behavior still sorts ascending.

Suggested tests:

- `best teams by defensive rating` -> `average_defensive_rating`, `ASC`.
- `worst teams by defensive rating` -> `average_defensive_rating`, `DESC`.
- `highest teams by defensive rating` -> `average_defensive_rating`, `DESC`.
- `lowest teams by defensive rating` -> `average_defensive_rating`, `ASC`.
- `top teams by net rating` -> `average_net_rating`, `DESC`.
- `bottom teams by net rating` -> `average_net_rating`, `ASC`.
- `fewest turnovers by players` -> turnover metric, `ASC`.
- `most turnovers by players` -> turnover metric, `DESC`.

## Slice 3: Ranking Presentation And End-To-End Behavior

Purpose:

Make answer synthesis describe direction-aware rankings correctly. SQL direction
alone is not enough, because `ASC` can mean either `bottom` or `best` depending
on the metric and user intent.

Problem example:

```text
best teams by defensive rating
```

The SQL should sort `ASC`, but the answer should not say:

```text
Bottom teams by defensive rating
```

It should say something like:

```text
Best teams by defensive rating
```

Implementation:

- Add a resolved ranking presentation field to the grounded query and execution
  plan. Possible shape:

```text
rank_intent_label: best | worst | top | bottom | highest | lowest | most | fewest | ranked
```

or:

```text
ranking_presentation:
  label: best
  leader_phrase: leads
  value_phrase: lowest
```

- Carry the field through:
  - `ResolvedMetricQuery`
  - execution plan
  - runtime models
  - `SynthesisPayload`
  - `FinalAnswer`

- Update:
  - `services/runtime-py/runtime/AnswerSynthesis/interpretation_summary.py`
  - `services/runtime-py/runtime/AnswerSynthesis/synthesize.py`
  - `services/runtime-py/runtime/AnswerSynthesis/format_response.py` if table
    labels need rank intent awareness
  - chart planning only if it uses rank direction language directly

Presentation examples:

```text
best + defensive_rating + ASC:
Best 10 teams by defensive rating.
The Thunder rank first with 106.2 defensive rating.
```

```text
fewest + turnovers + ASC:
Fewest 10 players by turnovers.
Player X has the fewest with 1.2 turnovers.
```

```text
bottom + net_rating + ASC:
Bottom 10 teams by net rating.
Team X is lowest with -8.4 net rating.
```

Done when:

- Direction-aware SQL and answer wording agree.
- `ASC` no longer automatically means `Bottom`.
- `best defense` can return ascending defensive rating while displaying as
  best, not bottom.
- Existing bottom/lowest wording still works for true bottom/lowest requests.

Suggested end-to-end tests:

- CLI or semantic pipeline test for `best defensive teams this season`.
- CLI or semantic pipeline test for `worst defensive teams this season`.
- CLI or semantic pipeline test for `fewest turnovers over the last 10 games`.
- Answer synthesis test proving `best defensive rating` does not say `Bottom`.
- Answer synthesis test proving `bottom net rating` still says `Bottom`.

## Cross-Slice Acceptance Criteria

This feature is complete when:

- Ranking polarity lives in ontology metric definitions, not scattered in prompt
  text or answer formatting.
- User rank intent is preserved as intent, not collapsed prematurely into raw
  `ASC` or `DESC`.
- Final sort direction is resolved after metric grounding.
- Presentation receives enough semantic context to describe the result
  naturally.
- The assistant can handle both quality language and quantity language:

```text
best defensive rating    -> lower is better -> ASC
highest defensive rating -> highest value    -> DESC
fewest turnovers         -> lowest value     -> ASC
most turnovers           -> highest value    -> DESC
```

- No new artificial restrictions are introduced above the schema contract.

## Non-Goals

This plan does not add new computed metrics such as `stocks`, `PRA`, or
`points + rebounds + assists`.

This plan does not solve broad intent phrases such as `protecting the ball` or
`crashing the glass` unless they already ground to executable ontology metrics.
Those should be handled by a later metric-intent expansion slice.

This plan does not make neutral metrics fail. For product flexibility, neutral
metrics should keep a sensible default direction unless the user gives explicit
direction language.
