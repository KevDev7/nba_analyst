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
  , resolveMetricFormulaWithColumn
  , resolveMetricFormulas
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Resolve.Common.Types
import OntologyLayer.Types (MetricDef (aggregation, executable, expression, name, source_attributes))
import QueryModel.IR

resolveMetricFormula :: MetricDef -> ResolvedMetricFormula
resolveMetricFormula metricDef =
  resolveMetricFormulaWithColumn "metric_value" metricDef

resolveMetricFormulaWithColumn :: Text -> MetricDef -> ResolvedMetricFormula
resolveMetricFormulaWithColumn resultColumnValue metricDef =
  ResolvedMetricFormula
    { metricKey = name metricDef
    , aggregationKind = aggregation metricDef
    , sourceAttributes = source_attributes metricDef
    , expressionText = expression metricDef
    , executableInSlice = executable metricDef
    , resultColumn = resultColumnValue
    }

resolveMetricFormulas :: [MetricDef] -> [ResolvedMetricFormula]
resolveMetricFormulas metricDefs =
  zipWith resolveMetricFormulaWithColumn resultColumns metricDefs
  where
    resultColumns =
      "metric_value" : ["metric_" <> T.pack (show indexValue) | indexValue <- [2 :: Int ..]]

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
  requireAtLeastOneMetricName
    "Ranking/aggregation metric queries require at least one selected metric."
    metricValues

requireTrendMetricName :: [MetricName] -> Either Text MetricName
requireTrendMetricName metricValues =
  requireExactlyOneMetricName
    "Trend queries require exactly one selected metric."
    metricValues

requireObjectQueryMetricName :: [MetricName] -> Either Text MetricName
requireObjectQueryMetricName metricValues =
  requireAtLeastOneMetricName
    "Object queries require at least one selected metric."
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

requireAtLeastOneMetricName :: Text -> [MetricName] -> Either Text MetricName
requireAtLeastOneMetricName cardinalityMessage metricValues =
  case metricValues of
    metricValue : _ -> Right metricValue
    [] -> Left cardinalityMessage
