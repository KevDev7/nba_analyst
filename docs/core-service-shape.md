# Core Service Shape

This doc captures the more faithful version of the core service we want to build.

It is intentionally narrower than full TextQL product scope, but it should preserve the main internal shape of the core analysis engine:

- ontology / semantic layer
- embeddings-assisted mapping
- ADT / tree-based internal representations
- validation and compilation
- iterative execution
- Python analysis
- final analytical answer synthesis

## What This Is

This is not just:

- user question -> SQL -> answer

It is closer to:

- user question
- semantic interpretation
- structured internal representation
- validated compilation
- iterative analysis runtime
- grounded answer

## Core End-to-End Flow

### 1. User Question

A user asks an open-ended analytics question.

Examples:

- "Why did the Knicks offense improve in the last 10 games?"
- "Who are the most improved young guards this season?"
- "Compare Brunson and Haliburton as scorers over the last month."

### 2. Semantic Interpretation

The semantic core interprets the question in business/data terms.

This stage should:

- identify candidate objects
- identify candidate metrics
- identify filters
- identify time windows
- identify comparisons / ranking intent
- identify analysis intent

This is where embeddings and lexical matching can help map natural-language phrases into ontology concepts.

### 3. Ontology Mapping

The system maps extracted concepts into the ontology / semantic layer.

This includes:

- object resolution
- metric resolution
- dimension resolution
- relationship / join-path resolution
- governed business-definition lookup

The ontology is the control surface that keeps the model from drifting into unconstrained text-to-SQL behavior.

### 4. ADT / Tree-Based Internal Representation

After mapping, the semantic core should build typed internal structures.

These should be:

- ADT-shaped
- tree-like where appropriate
- explicit enough that invalid states are hard to represent

Examples of internal structures we likely want:

- resolved semantic request
- query intent tree
- validated analysis plan
- executable query plan

The point is that the system should reason over structured representations, not loose dictionaries and strings.

### 5. Validation

Before execution, the system validates the mapped request and internal plan.

This should catch:

- undefined metrics
- unsupported dimensions
- invalid filters
- unsafe or missing join paths
- ambiguous or unresolved business terms
- unsupported analysis shapes

Validation is a core part of the product, not a final cleanup pass.

### 6. Compilation

Once validated, the semantic core compiles the structured representation into executable query steps.

This does not have to be "one SQL string only."

It may compile into:

- one SQL query
- multiple SQL queries
- SQL + Python analysis steps
- staged execution plans

The compiler should preserve:

- governed metric logic
- safe relationships
- explicit analytical intent

### 7. Iterative Runtime Execution

The runtime executes the compiled plan and persists intermediate artifacts.

This stage should support:

- SQL execution
- storing intermediate results outside the model context window
- rerunning or extending analysis based on prior results
- multi-step investigation

This is where the system behaves more like an analyst than a one-shot query generator.

### 8. Python Analysis Layer

After query execution, the runtime should be able to perform deeper analysis in Python.

Examples:

- reshaping / aggregation
- comparisons
- trends
- deltas
- ranking logic
- significance testing
- derived computations

This is important because real analysis is often more than "run one query and summarize rows."

### 9. Answer Synthesis

The final layer turns the analytical work into a usable answer.

It should produce:

- findings
- explanation
- caveats / limitations
- optional supporting tables/charts

The output should read like analysis, not just like a query result dump.

## Internal Shape We Want To Preserve

If we compress the real core into one line, it is:

`question -> semantic interpretation -> ontology mapping -> ADT/tree IR -> validation -> compilation -> iterative execution -> Python analysis -> answer synthesis`

That is the service shape we want to preserve.

## What Matters Most

The key things not to accidentally simplify away are:

- ontology-first grounding
- embeddings-assisted semantic mapping
- ADT / tree-based internal modeling
- validation before trust
- compiler-like transformation into execution steps
- iterative runtime behavior
- Python/statistical analysis as part of the core

## What Is Still Open

We still need to decide:

- the exact ontology types
- the exact ADTs / trees
- the exact IR / DSL boundary
- where embeddings are used directly
- how many compilation stages exist
- how much iteration is owned by the semantic core vs runtime
