-- Purpose:
-- Load the live ontology fixture from disk.
--
-- Uses:
-- - the YAML ontology file in fixtures/ontology
--
-- Produces:
-- - a typed Ontology value
--
-- Next:
-- - Graph.hs

module OntologyLayer.Load where

import Data.Yaml (decodeFileThrow)
import OntologyLayer.Types (Ontology)

loadOntology :: FilePath -> IO Ontology
loadOntology = decodeFileThrow
