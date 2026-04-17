-- Purpose:
-- Provide ontology lookup helpers for live grounding and validation.
--
-- Uses:
-- - typed ontology values from Types.hs
--
-- Produces:
-- - object, attribute, and metric lookup functions
--
-- Next:
-- - QueryModel/Match.hs or GroundedPlanning/Validation.hs

module OntologyLayer.Graph where

import Data.List (find)
import Data.Text (Text)
import OntologyLayer.Types

findObject :: Ontology -> Text -> Maybe Object
findObject ontology objectName = find matchesObject (objects ontology)
  where
    matchesObject Object {name = currentName} = currentName == objectName

findAttribute :: Object -> Text -> Maybe Attribute
findAttribute object attributeName = find matchesAttribute (attributes object)
  where
    matchesAttribute Attribute {name = currentName} = currentName == attributeName

findMetric :: Object -> Text -> Maybe MetricDef
findMetric object metricName = find matchesMetric (metrics object)
  where
    matchesMetric MetricDef {name = currentName} = currentName == metricName

findLink :: Ontology -> Text -> Text -> Maybe Link
findLink ontology sourceName targetName = find matchesLink (links ontology)
  where
    matchesLink Link {source_object = currentSource, target_object = currentTarget} =
      currentSource == sourceName && currentTarget == targetName
