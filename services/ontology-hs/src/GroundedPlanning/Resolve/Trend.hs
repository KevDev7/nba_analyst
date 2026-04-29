{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Ground trend/time-series queries into concrete runtime details.

module GroundedPlanning.Resolve.Trend where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common
import OntologyLayer.Types (Object (backing_table), Ontology)
import QueryModel.IR

resolveTrendQuery :: Ontology -> MetricQuerySpec -> Either Text ResolvedTrendQuery
resolveTrendQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
      maybeTrendTimeGrain =
        case base of
          BaseQuery {timeGrain = currentTimeGrain} -> currentTimeGrain
  trendTimeGrain <- requireTrendTimeGrainValue maybeTrendTimeGrain
  factObject <- requireObject ontology (coreFactObject base)
  selectedMetrics <- requireTrendMetricNames (metrics base)
  metricDefs <- mapM (requireMetric factObject) selectedMetrics
  metricDef <-
    case metricDefs of
      selectedMetric : _ -> Right selectedMetric
      [] -> Left "Trend queries require at least one selected metric."
  resolvedGroupingDimensionValues <- resolveTrendGroupingDimensions ontology (coreFactObject base) (dimensions base)
  let resolvedGroupingDimensions =
        map (\(_, _, groupingDimension) -> groupingDimension) resolvedGroupingDimensionValues
      resolvedSeries =
        case resolvedGroupingDimensionValues of
          firstGrouping : _ -> Just firstGrouping
          [] -> Nothing
  metricSourceColumn <- metricSourceAttribute metricDef
  resolvedRowPredicate <- resolveBaseRowPredicate ontology (coreFactObject base) (rowPredicate base)
  resolvedResultPredicate <- resolveBaseResultPredicate factObject metricDef (resultPredicate base)
  let maybeSeasonPair = seasonFilterPair (filters base)
  pure
    ResolvedTrendQuery
      { factTableName = backing_table factObject
      , seriesTableName = (\(seriesObject, _, _) -> backing_table seriesObject) <$> resolvedSeries
      , seriesObjectName = (\(seriesObject, _, _) -> objectName seriesObject) <$> resolvedSeries
      , seriesPath = (\(_, seriesPathValue, _) -> seriesPathValue) <$> resolvedSeries
      , seriesName =
          case resolvedGroupingDimensions of
            groupingDimension : _ -> Just (ColumnRef "group" (columnName (groupingSource groupingDimension)))
            [] -> Nothing
      , timeBucketName = "time_bucket"
      , timeBucketExpression = timeBucketExpressionFor trendTimeGrain
      , metricSource = ColumnRef "fact" metricSourceColumn
      , metricFormula = resolveMetricFormula metricDef
      , trendDisplayMetricFormulas = resolveMetricFormulas metricDefs
      , filterLocation = "fact_table"
      , timeFilterKind = trendFilterKindText (filters base)
      , trendFilters = filters base
      , timeGrain = timeGrainText trendTimeGrain
      , trendSeasonLabel = fst <$> maybeSeasonPair
      , trendSeasonType = snd <$> maybeSeasonPair
      , trendRowPredicateResolved = resolvedRowPredicate
      , trendResultPredicateResolved = resolvedResultPredicate
      , trendGroupingDimensions = resolvedGroupingDimensions
      , resolvedAssumptions = assumptions base
      }
