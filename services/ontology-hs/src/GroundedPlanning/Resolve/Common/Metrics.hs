{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Metrics
  ( metricSourceAttribute
  , orderDirectionText
  , requireComparisonMetricName
  , requireExactlyOneMetricName
  , requireObjectQueryMetricName
  , requireOrdinaryMetricName
  , requireTrendMetricName
  , resolveEntity
  , resolveMetricFormula
  ) where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common.Types
import OntologyLayer.Types (MetricDef (aggregation, executable, expression, name, source_attributes))
import QueryModel.IR

resolveMetricFormula :: MetricDef -> ResolvedMetricFormula
resolveMetricFormula metricDef =
  ResolvedMetricFormula
    { metricKey = name metricDef
    , aggregationKind = aggregation metricDef
    , sourceAttributes = source_attributes metricDef
    , expressionText = expression metricDef
    , executableInSlice = executable metricDef
    , resultColumn = "metric_value"
    }

orderDirectionText :: [Order] -> Text
orderDirectionText orderValues =
  case orderValues of
    Asc _ : _ -> "ASC"
    Desc _ : _ -> "DESC"
    [] -> "DESC"

resolveEntity :: EntityRef -> ResolvedEntity
resolveEntity entityRefValue =
  ResolvedEntity
    { entityIdValue =
        case entityRefValue of
          EntityRef {entityId = currentEntityId} -> currentEntityId
    , entityName =
        case entityRefValue of
          EntityRef {entityName = currentEntityName} -> currentEntityName
    }

metricSourceAttribute :: MetricDef -> Either Text Text
metricSourceAttribute metricDef =
  case source_attributes metricDef of
    sourceAttribute : _ -> Right sourceAttribute
    [] -> Left "Selected metric must reference at least one source attribute."

requireOrdinaryMetricName :: [MetricName] -> Either Text MetricName
requireOrdinaryMetricName metricValues =
  requireExactlyOneMetricName
    "Ranking/aggregation metric queries require exactly one selected metric."
    metricValues

requireTrendMetricName :: [MetricName] -> Either Text MetricName
requireTrendMetricName metricValues =
  requireExactlyOneMetricName
    "Trend queries require exactly one selected metric."
    metricValues

requireObjectQueryMetricName :: [MetricName] -> Either Text MetricName
requireObjectQueryMetricName metricValues =
  requireExactlyOneMetricName
    "Object queries require exactly one selected metric."
    metricValues

requireComparisonMetricName :: [MetricName] -> Either Text MetricName
requireComparisonMetricName metricValues =
  requireExactlyOneMetricName
    "Comparison queries require exactly one selected metric."
    metricValues

requireExactlyOneMetricName :: Text -> [MetricName] -> Either Text MetricName
requireExactlyOneMetricName cardinalityMessage metricValues =
  case metricValues of
    [metricValue] -> Right metricValue
    _ -> Left cardinalityMessage
