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
  (rowObject, discoveredRowPath) <-
    resolveOrdinaryMetricRowObject ontology (coreFactObject base) (dimensions base)
  selectedMetric <- requireOrdinaryMetricName (metrics base)
  metricDef <- requireMetric factObject selectedMetric
  displayColumn <- metricDisplayColumn (dimensions base)
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObject
  resolvedLinkedFilters <- mapM (resolveLinkedFilter ontology (coreFactObject base)) (linkedFilters base)
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
      , displayName = ColumnRef "row" displayColumn
      , contextValue = Nothing
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
      , displayMetadata = resolveDisplayMetadata factObject rowObject gamesValue
      }
