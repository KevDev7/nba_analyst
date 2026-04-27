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

import Data.Text (Text)
import qualified Data.Text as T
import Data.Yaml (decodeFileEither, prettyPrintParseException)
import OntologyLayer.Types (Ontology)
import OntologyLayer.Validation (validateOntology)

loadOntology :: FilePath -> IO Ontology
loadOntology path = do
  -- Convenience wrapper for callers that want an Ontology or a thrown IO failure.
  loaded <- loadOntologyEither path
  case loaded of
    Right ontology -> pure ontology
    Left err -> fail (T.unpack err)

loadOntologyEither :: FilePath -> IO (Either Text Ontology)
loadOntologyEither path = do
  -- Read semantic-gold.yaml and decode it into the Types.hs ontology structures.
  decoded <- decodeFileEither path
  pure $
    case decoded of
      Left err -> Left (T.pack (prettyPrintParseException err))
      Right ontology ->
        -- Only return the ontology if it passes the semantic contract checks.
        case validateOntology ontology of
          Right () -> Right ontology
          Left validationErr -> Left validationErr
