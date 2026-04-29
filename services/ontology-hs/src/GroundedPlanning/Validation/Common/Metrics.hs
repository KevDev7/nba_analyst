{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Metrics
  ( requireComparisonSelectedMetric
  , requireComparisonSelectedMetrics
  , requireFamilySelectedMetric
  , requireObjectQuerySelectedMetric
  , requireOrdinaryMetricSelectedMetric
  , requireTrendSelectedMetric
  , requireTrendSelectedMetrics
  , validateMetricAttributes
  ) where

import Data.Text (Text)
import OntologyLayer.Types (MetricDef (executable, name, source_attributes), Object)
import qualified OntologyLayer.Types as OT
import QueryModel.IR (MetricName)
import GroundedPlanning.Validation.Common.Ontology (requireMetric)

requireOrdinaryMetricSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireOrdinaryMetricSelectedMetric factObject metricValues =
  requireAtLeastOneSelectedMetric
    "Ranking/aggregation metric queries require at least one selected metric."
    factObject
    metricValues

requireTrendSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireTrendSelectedMetric factObject metricValues =
  requireAtLeastOneSelectedMetric
    "Trend queries require at least one selected metric."
    factObject
    metricValues

requireTrendSelectedMetrics :: Object -> [MetricName] -> Either Text [OT.MetricDef]
requireTrendSelectedMetrics factObject metricValues =
  requireExecutableMetrics
    "Trend queries require at least one selected metric."
    factObject
    metricValues

requireComparisonSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireComparisonSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Comparison queries require exactly one selected metric."
    factObject
    metricValues

requireComparisonSelectedMetrics :: Object -> [MetricName] -> Either Text [OT.MetricDef]
requireComparisonSelectedMetrics factObject metricValues =
  requireExecutableMetrics
    "Comparison queries require at least one selected metric."
    factObject
    metricValues

requireObjectQuerySelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireObjectQuerySelectedMetric factObject metricValues =
  requireAtLeastOneSelectedMetric
    "Object queries require at least one selected metric."
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

requireAtLeastOneSelectedMetric :: Text -> Object -> [MetricName] -> Either Text OT.MetricDef
requireAtLeastOneSelectedMetric cardinalityMessage factObject metricValues =
  case requireExecutableMetrics cardinalityMessage factObject metricValues of
    Right (selectedMetric : _) -> Right selectedMetric
    Right [] -> Left cardinalityMessage
    Left message -> Left message

requireExecutableMetrics :: Text -> Object -> [MetricName] -> Either Text [OT.MetricDef]
requireExecutableMetrics cardinalityMessage factObject metricValues =
  case metricValues of
    [] -> Left cardinalityMessage
    _ : _ -> mapM (requireExecutableMetric factObject) metricValues

requireExecutableMetric :: Object -> MetricName -> Either Text OT.MetricDef
requireExecutableMetric factObject metricValue = do
  metricDef <- requireMetric factObject metricValue
  if executable metricDef
    then pure metricDef
    else Left ("Metric '" <> name metricDef <> "' is present in the ontology but not executable in this slice.")

validateMetricAttributes :: OT.MetricDef -> Either Text ()
validateMetricAttributes metricDef =
  if null (source_attributes metricDef)
    then Left ("Metric '" <> name metricDef <> "' must reference at least one source attribute.")
    else Right ()
