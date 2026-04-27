{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Ground object-row queries into concrete runtime details.

module GroundedPlanning.Resolve.Object where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common
import OntologyLayer.Types (Object (backing_table), Ontology)
import QueryModel.IR

resolveObjectQuery :: Ontology -> ObjectQuerySpec -> Either Text ResolvedObjectQuery
resolveObjectQuery ontology objectQuery = do
  let base =
        case objectQuery of
          ObjectQuerySpec {sharedQuery = currentBase} -> currentBase
      rowObjectNameValue =
        case objectQuery of
          ObjectQuerySpec {rowObject = currentRowObject} -> currentRowObject
  factObject <- requireObject ontology (coreFactObject base)
  rowObjectValue <- requireObject ontology rowObjectNameValue
  discoveredRowPath <- requirePath ontology (coreFactObject base) rowObjectNameValue
  selectedMetric <- requireObjectQueryMetricName (metrics base)
  metricDef <- requireMetric factObject selectedMetric
  displayColumn <- metricDisplayColumn (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObjectValue
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObjectValue
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
    ResolvedObjectQuery
      { rowTableName = backing_table rowObjectValue
      , factTableName = backing_table factObject
      , rowObjectName = rowObjectNameValue
      , objectOrderDirection = orderDirectionText (orders base)
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
      , resolvedAssumptions = assumptions base
      , metricFormula = resolveMetricFormula metricDef
      , filterLocation = "fact_table"
      }
