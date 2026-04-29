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
  metricDefs <- mapM (requireMetric factObject) (metrics base)
  displayColumn <- metricDisplayColumn (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObjectValue
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObjectValue
  resolvedRowPredicate <- resolveBaseRowPredicate ontology (coreFactObject base) (rowPredicate base)
  resolvedResultPredicate <- resolveBaseResultPredicate factObject metricDef (resultPredicate base)
  let maybeSeasonPair = seasonFilterPair (filters base)
      gamesValue =
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
      , timeFilterKind = metricTimeFilterKind (filters base)
      , timeFilters = filters base
      , seasonLabel = fst <$> maybeSeasonPair
      , seasonType = snd <$> maybeSeasonPair
      , queryLimit = limit base
      , objectRowPredicateResolved = resolvedRowPredicate
      , objectResultPredicateResolved = resolvedResultPredicate
      , resolvedAssumptions = assumptions base
      , metricFormula = resolveMetricFormula metricDef
      , displayMetricFormulas = resolveMetricFormulas metricDefs
      , filterLocation = "fact_table"
      , displayMetadata = resolveDisplayMetadata factObject rowObjectValue gamesValue
      }
