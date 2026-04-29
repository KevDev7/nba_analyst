-- Purpose:
-- Validation rules for object-row queries.

module GroundedPlanning.Validation.Object where

import Data.Text (Text)
import GroundedPlanning.Validation.Common
import OntologyLayer.Types (Ontology)
import QueryModel.IR

validateObjectQuery :: Ontology -> ObjectQuerySpec -> Either Text ()
validateObjectQuery ontology objectQuery = do
  let base =
        case objectQuery of
          ObjectQuerySpec {sharedQuery = currentBase} -> currentBase
  validateObjectQueryTimeGrain (timeGrain base)
  factObject <- requireObject ontology (coreFactObject base)
  let rowObjectNameValue = rowObject objectQuery
  _ <- requirePath ontology (objectName factObject) rowObjectNameValue
  metricDef <- requireObjectQuerySelectedMetric factObject (metrics base)
  validateMetricAttributes metricDef
  mapM_ (validateResultPredicateTree factObject metricDef) (resultPredicate base)
  rowObjectValue <- requireObject ontology rowObjectNameValue
  requireObjectQueryDimension rowObjectValue (dimensions base)
  _ <- classifyOrdinaryMetricFilterFamily (filters base)
  mapM_ (validateRowPredicateTree ontology (objectName factObject)) (rowPredicate base)
  validateOrdinaryMetricFilterSurface factObject (filters base)
  validateOptionalMetricOrder (orders base) (metrics base)
