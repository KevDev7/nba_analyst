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
- interpret the supported metric and object query families
- emit typed IR and execution plans as JSON
