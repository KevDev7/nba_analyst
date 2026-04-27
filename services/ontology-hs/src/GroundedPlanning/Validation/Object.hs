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
  rowObjectValue <- requireObject ontology rowObjectNameValue
  requireObjectQueryDimension rowObjectValue (dimensions base)
  filterFamily <- classifyOrdinaryMetricFilterFamily (filters base)
  validateOrdinaryLinkedFilters ontology ObjectLinkedFilterQuery filterFamily (objectName factObject) (linkedFilters base)
  validateOptionalMetricOrder (orders base) (metrics base)
