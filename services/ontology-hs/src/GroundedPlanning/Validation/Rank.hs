-- Purpose:
-- Validation rules for ranking/aggregation-style metric queries.

module GroundedPlanning.Validation.Rank where

import Data.Text (Text)
import GroundedPlanning.Validation.Common
import OntologyLayer.Types (Ontology)
import QueryModel.IR

validateRankMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ()
validateRankMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  metricDef <- requireOrdinaryMetricSelectedMetric factObject (metrics base)
  validateMetricAttributes metricDef
  _ <- requireOrdinaryMetricRowObject ontology factObject (dimensions base)
  filterFamily <- classifyOrdinaryMetricFilterFamily (filters base)
  validateOrdinaryLinkedFilters ontology MetricLinkedFilterQuery filterFamily (objectName factObject) (linkedFilters base)
  validateOrdinaryMetricFilterSurface factObject (filters base)
  validateMetricOrders Nothing (orders base) (metrics base)
