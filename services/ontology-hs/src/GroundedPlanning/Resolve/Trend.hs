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
  selectedMetric <- requireTrendMetricName (metrics base)
  metricDef <- requireMetric factObject selectedMetric
  resolvedSeries <- resolveTrendSeries ontology factObject (dimensions base)
  metricSourceColumn <- metricSourceAttribute metricDef
  resolvedLinkedFilters <- mapM (resolveLinkedFilter ontology (coreFactObject base)) (linkedFilters base)
  pure
    ResolvedTrendQuery
      { factTableName = backing_table factObject
      , seriesTableName = backing_table . fst <$> resolvedSeries
      , seriesObjectName = objectName . fst <$> resolvedSeries
      , seriesPath = snd <$> resolvedSeries
      , seriesName = fmap (\(seriesObject, _) -> ColumnRef "series" (trendSeriesColumn seriesObject (dimensions base))) resolvedSeries
      , timeBucketName = "time_bucket"
      , timeBucketExpression = timeBucketExpressionFor trendTimeGrain
      , metricSource = ColumnRef "fact" metricSourceColumn
      , metricFormula = resolveMetricFormula metricDef
      , filterLocation = "fact_table"
      , timeFilterKind = trendFilterKindText (filters base)
      , trendFilters = filters base
      , timeGrain = timeGrainText trendTimeGrain
      , linkedFiltersResolved = resolvedLinkedFilters
      , resolvedAssumptions = assumptions base
      }
