# Ontology Service

This service is intended to mirror the core part of the TextQL-style architecture we care about most.

Primary responsibilities:

- define ontology types
- define ADT-based query IR / DSL
- resolve user intent into ontology concepts
- validate requests against business/data definitions
- compile validated plans for execution

Initial implementation target:

- Haskell

Current live responsibility:

- load the gold-first NBA ontology fixture
- interpret supported semantic drafts into typed query IR
- validate, resolve, and compile metric, object, and find query families
- ground metrics, dimensions, predicates, values, links, and time scopes
- emit typed IR and execution plans as JSON
