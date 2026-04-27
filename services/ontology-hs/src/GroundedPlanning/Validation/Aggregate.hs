-- Purpose:
-- Validation rules for grouped aggregate metric queries.

{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Aggregate where

import Data.Text (Text)
import GroundedPlanning.Validation.Common
import OntologyLayer.Types (Ontology)
import QueryModel.IR

validateAggregateMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ()
validateAggregateMetricQuery ontology metricQuery = do
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
  validateAggregateOrders (orders base)
  validateAggregateLimit (limit base)

validateAggregateOrders :: [Order] -> Either Text ()
validateAggregateOrders orderValues =
  if null orderValues
    then pure ()
    else Left "Aggregate queries should not request ranking order."

validateAggregateLimit :: Maybe Int -> Either Text ()
validateAggregateLimit maybeLimit =
  case maybeLimit of
    Nothing -> pure ()
    Just limitValue
      | limitValue > 0 -> pure ()
      | otherwise -> Left "Aggregate query limit must be positive when provided."
