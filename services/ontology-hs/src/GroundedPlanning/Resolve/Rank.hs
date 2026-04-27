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
  (rowObject, discoveredRowPath) <-
    resolveOrdinaryMetricRowObject ontology (coreFactObject base) (dimensions base)
  selectedMetric <- requireOrdinaryMetricName (metrics base)
  metricDef <- requireMetric factObject selectedMetric
  displayColumn <- metricDisplayColumn (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObject
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObject
  resolvedLinkedFilters <- mapM (resolveLinkedFilter ontology (coreFactObject base)) (linkedFilters base)
  let maybeSeasonPair = seasonFilterPair (filters base)
      gamesValue =
        case maybeSeasonPair of
          Just _ -> 0
          Nothing ->
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
      , rowPath = discoveredRowPath
      , contextPath = selectedContextPath contextSelection
      , partitionKey = pathPartitionKey rowPrimaryKey discoveredRowPath
      , entityId = ColumnRef "row" rowPrimaryKey
      , displayName = ColumnRef "row" displayColumn
      , contextValue = selectedContextColumn contextSelection
      , gameDate = ColumnRef "fact" "game_date"
      , metricSource = ColumnRef "fact" metricSourceColumn
      , windowGames = gamesValue
      , seasonLabel = fst <$> maybeSeasonPair
      , seasonType = snd <$> maybeSeasonPair
      , queryLimit = limit base
      , linkedFiltersResolved = resolvedLinkedFilters
      , comparisonEntities = []
      , comparisonRequestedValue = False
      , resolvedAssumptions = assumptions base
      , metricFormula = resolveMetricFormula metricDef
      , filterLocation = "fact_table"
      }
