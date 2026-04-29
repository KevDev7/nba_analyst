{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Ground grouped aggregate metric queries into concrete runtime details.

module GroundedPlanning.Resolve.Aggregate where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common
import OntologyLayer.Types (Object (backing_table), Ontology)
import QueryModel.IR

resolveAggregateMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ResolvedMetricQuery
resolveAggregateMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  groupingValues <-
    resolveAggregateGroupingDimensions ontology (coreFactObject base) (dimensions base)
  (rowObject, discoveredRowPath, firstGroupingDimension) <-
    case groupingValues of
      firstGroupingValue : _ -> Right firstGroupingValue
      [] -> Left "Aggregate queries require at least one business grouping dimension."
  let resolvedGroupingDimensions = map (\(_, _, groupingDimension) -> groupingDimension) groupingValues
  selectedMetric <- requireOrdinaryMetricName (metrics base)
  metricDef <- requireMetric factObject selectedMetric
  metricDefs <- mapM (requireMetric factObject) (metrics base)
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObject
  resolvedRowPredicate <- resolveBaseRowPredicate ontology (coreFactObject base) (rowPredicate base)
  resolvedResultPredicate <- resolveBaseResultPredicate factObject metricDef (resultPredicate base)
  let maybeSeasonPair = seasonFilterPair (filters base)
      gamesValue =
        case requireLastNGames (filters base) of
          Right value -> value
          Left _ -> 0
  pure
    ResolvedMetricQuery
      { factTableName = backing_table factObject
      , rowTableName = backing_table rowObject
      , rowObjectName = objectName rowObject
      , metricResultShape = "aggregate"
      , metricOrderDirection = "ASC"
      , rowPath = discoveredRowPath
      , contextPath = Nothing
      , partitionKey = pathPartitionKey rowPrimaryKey discoveredRowPath
      , entityId = ColumnRef "row" rowPrimaryKey
      , displayName = groupingSource firstGroupingDimension
      , contextValue = Nothing
      , gameDate = ColumnRef "fact" "game_date"
      , metricSource = ColumnRef "fact" metricSourceColumn
      , metricTimeGrain = Nothing
      , metricTimeBucketExpression = Nothing
      , windowGames = gamesValue
      , timeFilterKind = metricTimeFilterKind (filters base)
      , timeFilters = filters base
      , seasonLabel = fst <$> maybeSeasonPair
      , seasonType = snd <$> maybeSeasonPair
      , queryLimit = limit base
      , rowPredicateResolved = resolvedRowPredicate
      , resultPredicateResolved = resolvedResultPredicate
      , comparisonEntities = []
      , comparisonRequestedValue = False
      , resolvedAssumptions = assumptions base
      , metricFormula = resolveMetricFormula metricDef
      , displayMetricFormulas = resolveMetricFormulas metricDefs
      , filterLocation = "fact_table"
      , groupingDimensions = resolvedGroupingDimensions
      , displayMetadata = resolveDisplayMetadata factObject rowObject gamesValue
      }
