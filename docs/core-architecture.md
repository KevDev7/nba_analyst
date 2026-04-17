# Core Architecture

This doc captures the narrowed architecture for the product we actually want to build in this repo.

## Product Thesis

The core capability is:

- open-ended user question
- semantic understanding of business/data concepts
- structured analytical planning
- iterative execution and analysis
- grounded answer synthesis

This is not a dashboard factory or a connector marketplace. It is an analytics agent.

## Core Stack

### 1. Semantic Layer

The semantic layer is the system's business/data understanding.

It should define:

- objects
- dimensions
- measures
- metrics
- relationships / join paths
- governed business definitions

### 2. Typed IR / DSL

The system should not jump directly from user question to raw SQL.

It should first construct a typed intermediate representation that captures:

- target objects
- requested metrics
- filters
- time windows
- comparisons
- grouping / ranking intent
- analysis intent

### 3. Validation + Compilation

The semantic core validates the IR against the ontology and then compiles it into executable plans.

The validation layer should catch:

- undefined metrics
- invalid field references
- unsafe joins
- invalid groupings
- unsupported question shapes

### 4. Execution + Analysis Runtime

The runtime executes queries and keeps intermediate artifacts outside the model context window.

It should support:

- SQL execution
- persisted intermediate results
- Python dataframe/statistical analysis
- iterative follow-up steps

### 5. Answer Synthesis

The final output should be an analytical answer, not a raw query dump.

It should include:

- findings
- explanation
- caveats
- optional supporting tables/charts

## Service Shape

### `services/ontology-hs`

Owns:

- ontology data types
- typed IR / DSL
- resolution
- validation
- compilation

### `services/runtime-py`

Owns:

- query execution
- artifact persistence
- Python/statistical analysis
- result shaping

### `services/orchestrator`

Owns:

- question intake
- coordination across services
- final response assembly

## First End-to-End Flow

The first credible flow should be:

1. user asks an NBA analytics question
2. orchestrator sends question to ontology service
3. ontology service returns validated semantic/query plan
4. runtime executes SQL
5. runtime performs any needed Python analysis
6. orchestrator returns final grounded answer
