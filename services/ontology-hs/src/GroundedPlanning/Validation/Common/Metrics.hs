{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Metrics
  ( requireComparisonSelectedMetric
  , requireFamilySelectedMetric
  , requireObjectQuerySelectedMetric
  , requireOrdinaryMetricSelectedMetric
  , requireTrendSelectedMetric
  , validateMetricAttributes
  ) where

import Data.Text (Text)
import OntologyLayer.Types (MetricDef (executable, name, source_attributes), Object)
import qualified OntologyLayer.Types as OT
import QueryModel.IR (MetricName)
import GroundedPlanning.Validation.Common.Ontology (requireMetric)

requireOrdinaryMetricSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireOrdinaryMetricSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Ranking/aggregation metric queries require exactly one selected metric."
    factObject
    metricValues

requireTrendSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireTrendSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Trend queries require exactly one selected metric."
    factObject
    metricValues

requireObjectQuerySelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireObjectQuerySelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Object queries require exactly one selected metric."
    factObject
    metricValues

requireComparisonSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireComparisonSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Comparison queries require exactly one selected metric."
    factObject
    metricValues

requireFamilySelectedMetric :: Text -> Object -> [MetricName] -> Either Text OT.MetricDef
requireFamilySelectedMetric cardinalityMessage factObject metricValues =
  case metricValues of
    [metricValue] -> do
      metricDef <- requireMetric factObject metricValue
      if executable metricDef
        then pure metricDef
        else Left ("Metric '" <> name metricDef <> "' is present in the ontology but not executable in this slice.")
    _ -> Left cardinalityMessage

validateMetricAttributes :: OT.MetricDef -> Either Text ()
validateMetricAttributes metricDef =
  if null (source_attributes metricDef)
    then Left ("Metric '" <> name metricDef <> "' must reference at least one source attribute.")
    else Right ()
