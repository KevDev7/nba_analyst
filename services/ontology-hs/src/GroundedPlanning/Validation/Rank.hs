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
  mapM_ (validateResultPredicateTree factObject metricDef) (resultPredicate base)
  _ <- requireRankGroupingDimensions ontology factObject (dimensions base)
  _ <- classifyOrdinaryMetricFilterFamily (filters base)
  mapM_ (validateRowPredicateTree ontology (objectName factObject)) (rowPredicate base)
  validateOrdinaryMetricFilterSurface factObject (filters base)
  validateMetricOrders Nothing (orders base) (metrics base)
