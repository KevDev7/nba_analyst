{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Ground ranking/aggregation-style metric queries into concrete runtime details.

module GroundedPlanning.Resolve.Rank where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common
import OntologyLayer.Types (Object (backing_table), Ontology)
import QueryModel.IR

resolveRankMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ResolvedMetricQuery
resolveRankMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  groupingDimensionValues <- resolveAggregateGroupingDimensions ontology (coreFactObject base) (dimensions base)
  let (rowObject, discoveredRowPath, firstGroupingDimension) =
        case groupingDimensionValues of
          firstGrouping : _ -> firstGrouping
          [] -> error "Ranking validation should require at least one grouping dimension."
      resolvedGroupingDimensions =
        map (\(_, _, groupingDimension) -> groupingDimension) groupingDimensionValues
  selectedMetric <- requireOrdinaryMetricName (metrics base)
  metricDef <- requireMetric factObject selectedMetric
  metricDefs <- mapM (requireMetric factObject) (metrics base)
  displayColumn <- metricDisplayColumn [groupingLabel firstGroupingDimension]
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObject
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObject
  let partitionColumn =
        if tableRole (groupingSource firstGroupingDimension) == "fact"
          then groupingSource firstGroupingDimension
          else pathPartitionKey rowPrimaryKey discoveredRowPath
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
      , metricResultShape = "ranking"
      , metricOrderDirection = orderDirectionText (orders base)
      , metricRankIntentLabel = rankIntentLabel metricQuery
      , rowPath = discoveredRowPath
      , contextPath = selectedContextPath contextSelection
      , partitionKey = partitionColumn
      , entityId = partitionColumn
      , displayName = ColumnRef "row" displayColumn
      , contextValue = selectedContextColumn contextSelection
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
