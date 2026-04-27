{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Ground comparison queries into concrete runtime details.

module GroundedPlanning.Resolve.Compare where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common
import OntologyLayer.Types (Object (backing_table), Ontology)
import QueryModel.IR

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
  selectedMetric <- requireComparisonMetricName (metrics base)
  metricDef <- requireMetric factObject selectedMetric
  displayColumn <- metricDisplayColumn (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObject
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObject
  resolvedLinkedFilters <- mapM (resolveLinkedFilter ontology (coreFactObject base)) (linkedFilters base)
  let entityValues =
        case comparison metricQuery of
          Just (CompareEntities _ entities) -> map resolveEntity entities
          Nothing -> []
      maybeSeasonPair = seasonFilterPair (filters base)
      gamesValue =
        case requireLastNGames (filters base) of
          Right value -> value
          Left _ -> 0
  pure
    ResolvedMetricQuery
      { factTableName = backing_table factObject
      , rowTableName = backing_table rowObject
      , rowObjectName = objectName rowObject
      , metricResultShape = "comparison"
      , metricOrderDirection = "DESC"
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
      , queryLimit = Nothing
      , linkedFiltersResolved = resolvedLinkedFilters
      , comparisonEntities = entityValues
      , comparisonRequestedValue = True
      , resolvedAssumptions = assumptions base
      , metricFormula = resolveMetricFormula metricDef
      , filterLocation = "fact_table"
      , displayMetadata = resolveDisplayMetadata factObject rowObject gamesValue
      }
