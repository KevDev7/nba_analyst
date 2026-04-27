{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Validation rules for trend/time-series metric queries.

module GroundedPlanning.Validation.Trend where

import Data.Text (Text)
import GroundedPlanning.Validation.Common
import OntologyLayer.Types (Ontology)
import QueryModel.IR

validateTrendMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ()
validateTrendMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  metricDef <- requireTrendSelectedMetric factObject (metrics base)
  validateMetricAttributes metricDef
  case timeGrain base of
    Just timeGrainValue -> GroundedPlanning.Validation.Common.validateTrendMetricQuery ontology factObject metricDef timeGrainValue base
    Nothing -> Left "Trend queries require a time grain."
