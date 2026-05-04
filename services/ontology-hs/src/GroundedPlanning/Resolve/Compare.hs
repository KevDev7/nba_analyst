{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Ground comparison queries into concrete runtime details.

module GroundedPlanning.Resolve.Compare where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common
import OntologyLayer.Types (Object (backing_table), Ontology)
import QueryModel.IR
import qualified QueryModel.IR as QI

resolveCompareMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ResolvedMetricQuery
resolveCompareMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  comparisonTargetObjectName <-
    case comparison metricQuery of
      Just (CompareEntities targetObjectName _) -> Right (Just targetObjectName)
      Nothing -> Right Nothing
  (rowObject, discoveredRowPath) <-
    resolveComparisonRowObject ontology (coreFactObject base) (dimensions base) comparisonTargetObjectName
  selectedMetrics <- requireComparisonMetricNames (metrics base)
  metricDefs <- mapM (requireMetric factObject) selectedMetrics
  metricDef <-
    case metricDefs of
      selectedMetric : _ -> Right selectedMetric
      [] -> Left "Comparison queries require at least one selected metric."
  displayColumn <- requireComparisonDimensionName (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObject
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObject
  resolvedRowPredicate <- resolveBaseRowPredicate ontology (coreFactObject base) (rowPredicate base)
  groupingDimensionValues <-
    case requireComparisonBreakdownDimensionNames (dimensions base) of
      [] -> Right []
      breakdownDimensions -> map (\(_, _, groupingDimension) -> groupingDimension) <$> resolveAggregateGroupingDimensions ontology (coreFactObject base) breakdownDimensions
  let entityValues =
        case comparison metricQuery of
          Just (CompareEntities _ entities) -> map resolveEntity entities
          Nothing -> []
      maybeSeasonPair = seasonFilterPair (filters base)
      gamesValue =
        case requireLastNGames (filters base) of
          Right value -> value
          Left _ -> 0
      maybeBaseTimeGrain = QI.timeGrain base
      maybeTimeBucketExpression = timeBucketExpressionFor <$> maybeBaseTimeGrain
  pure
    ResolvedMetricQuery
      { factTableName = backing_table factObject
      , rowTableName = backing_table rowObject
      , rowObjectName = objectName rowObject
      , metricResultShape = "comparison"
      , metricOrderDirection = "DESC"
      , metricRankIntentLabel = Nothing
      , rowPath = discoveredRowPath
      , contextPath = selectedContextPath contextSelection
      , partitionKey = pathPartitionKey rowPrimaryKey discoveredRowPath
      , entityId = ColumnRef "row" rowPrimaryKey
      , displayName = ColumnRef "row" displayColumn
      , contextValue = selectedContextColumn contextSelection
      , gameDate = ColumnRef "fact" "game_date"
      , metricSource = ColumnRef "fact" metricSourceColumn
      , metricTimeGrain = QI.timeGrainText <$> maybeBaseTimeGrain
      , metricTimeBucketExpression = maybeTimeBucketExpression
      , windowGames = gamesValue
      , timeFilterKind = metricTimeFilterKind (filters base)
      , timeFilters = filters base
      , seasonLabel = fst <$> maybeSeasonPair
      , seasonType = snd <$> maybeSeasonPair
      , queryLimit = Nothing
      , rowPredicateResolved = resolvedRowPredicate
      , resultPredicateResolved = Nothing
      , comparisonEntities = entityValues
      , comparisonRequestedValue = True
      , resolvedAssumptions = assumptions base
      , metricFormula = resolveMetricFormula metricDef
      , displayMetricFormulas = resolveMetricFormulas metricDefs
      , filterLocation = "fact_table"
      , groupingDimensions = groupingDimensionValues
      , displayMetadata = resolveDisplayMetadata factObject rowObject gamesValue
      }
