# First Slice

This doc defines the first end-to-end question family we want to support.

The goal of the first slice is not to support every analytics question shape.
It is to make one useful question family work all the way through:

- ontology layer
- query model
- grounded planning
- analysis runtime
- answer synthesis

## First Question Family

### Data Exploration / Ranking / Top-N

Canonical example:

- "Show me the top 10 customers by revenue"

NBA-flavored version:

- "Show me the top 10 players by points over the last 10 games"

## Why Start Here

This is a good first slice because it is narrow without forcing a tool-picker architecture.

It exercises:

- a core fact object
- a measure or metric
- a ranking intent
- a limit
- optional filters or time windows
- answer formatting as a ranked result

It is also simple enough that we do not need charts, scenario modeling, or complex multi-step hypothesis testing on day one.

## What This Slice Should Cover

At minimum, this slice should support:

- identify the ranking target
- identify the core object
- identify the requested metric
- identify a time window if present
- identify a top-N or bottom-N constraint
- compile to executable query logic
- return a grounded ranked answer

## What This Slice Does Not Need Yet

For the first pass, this slice does not need:

- broad open-ended causal analysis
- correlation questions
- scenario / what-if modeling
- dashboard reuse
- web search
- multi-source joins across many systems
- rich chart generation

## Success Criteria

We should consider this slice successful when:

- a user can ask a Top-N style question in natural language
- the system maps it into the ontology correctly
- the system builds a typed query model / IR
- the system produces a grounded execution plan
- the runtime executes the plan correctly
- the final answer is a ranked analytical response, not just raw SQL

## Adjacent Question Families For Later

After this slice works, likely next families are:

- aggregation / breakdown
- trend analysis
- filtering + joining
- comparison
- change over time
