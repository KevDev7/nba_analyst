{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Validation rules for comparison queries between named entities.

module GroundedPlanning.Validation.Compare where

import Data.Text (Text)
import GroundedPlanning.Validation.Common
import OntologyLayer.Types (Ontology)
import QueryModel.IR

validateCompareMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ()
validateCompareMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  case comparison metricQuery of
    Just comparisonIntent@(CompareEntities _ entities) -> do
      metricDef <- requireComparisonSelectedMetric factObject (metrics base)
      validateMetricAttributes metricDef
      rowObject <- requireComparisonRowObject ontology factObject (dimensions base) comparisonIntent
      validateComparisonQuery ontology factObject rowObject metricDef base comparisonIntent entities
    Nothing -> Left "Comparison validation requires a comparison intent."
