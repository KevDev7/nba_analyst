{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Aggregate (compileAggregateSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve

-- Build SQL for grouped aggregate questions.
-- This uses the same ontology-resolved fact/row paths as ranking, but returns
-- a summary table without rank numbering.
compileAggregateSql :: ResolvedMetricQuery -> Text
compileAggregateSql resolved@ResolvedMetricQuery {seasonLabel = maybeSeasonLabel, seasonType = maybeSeasonType, windowGames = metricWindowGamesValue} =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue)
      | metricWindowGamesValue <= 0 ->
      compileSeasonAggregateSql resolved seasonLabelValue seasonTypeValue
    _ ->
      let
        ResolvedMetricQuery
          { partitionKey = metricPartitionKey
          , rowPath = metricRowPath
          , displayName = metricDisplayName
          , contextValue = metricContextValue
          , gameDate = metricGameDate
          , metricSource = metricMetricSource
          , factTableName = metricFactTableName
          , metricFormula = resolvedMetricFormulaValue
          , windowGames = metricWindowGames
          , displayMetadata = metricDisplayMetadata
          , seasonLabel = metricSeasonLabel
          , seasonType = metricSeasonType
          , queryLimit = metricQueryLimit
          , linkedFiltersResolved = metricLinkedFilters
          } = resolved
        baseWhereConditions =
          renderSeasonFilterConditions "f" metricSeasonLabel metricSeasonType
            <> renderLinkedFilterConditions "f" metricLinkedFilters
        baseWhereClause =
          case baseWhereConditions of
            [] -> []
            conditions -> ["  WHERE " <> combineWhereClauses conditions]
       in
      T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_source,"
        ]
          <> renderMetadataSourceSelectLines "f" "r" "c" metricDisplayMetadata
          <> [ "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" metricPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
          <> baseWhereClause
          <> [ "), aggregate_groups AS ("
        , "  SELECT"
        , "    entity_name,"
        , "    MAX(context_value) AS context_value,"
        ]
          <> renderMetadataAggregateSelectLines metricDisplayMetadata
          <> [ "    " <> compileMetricAggregation resolvedMetricFormulaValue <> " AS metric_value"
        , "  FROM recent_rows"
        , "  WHERE game_rank <= " <> T.pack (show metricWindowGames)
        , "  GROUP BY entity_name"
        , ")"
        , "SELECT"
        , "  entity_name,"
        , "  context_value,"
        ]
          <> renderMetadataFinalSelectLines metricDisplayMetadata
          <> [ "  metric_value"
        , "FROM aggregate_groups"
        , "ORDER BY entity_name ASC"
        ]
          <> limitClause metricQueryLimit

-- Special SQL path for season-level aggregate questions.
compileSeasonAggregateSql :: ResolvedMetricQuery -> Text -> Text -> Text
compileSeasonAggregateSql resolved seasonLabelValue seasonTypeValue =
  let
    ResolvedMetricQuery
      { displayName = metricDisplayName
      , contextValue = metricContextValue
      , metricSource = metricMetricSource
      , factTableName = metricFactTableName
      , rowPath = metricRowPath
      , metricFormula = metricFormulaValue
      , queryLimit = metricQueryLimit
      , linkedFiltersResolved = metricLinkedFilters
      , displayMetadata = metricDisplayMetadata
      } = resolved
   in
  T.unlines $
    [ "WITH season_rows AS ("
    , "  SELECT"
    , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
    , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
    , "    " <> renderMetricValue metricMetricSource <> " AS metric_source,"
    ]
      <> renderMetadataSourceSelectLines "f" "r" "c" metricDisplayMetadata
      <> [ "    1 AS __metadata_row"
    , "  FROM " <> metricFactTableName <> " f"
    ]
      <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
      <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
      <> [ "  WHERE " <> combineWhereClauses (seasonWhereClause seasonLabelValue seasonTypeValue : renderLinkedFilterConditions "f" metricLinkedFilters)
         , "    AND " <> renderMetricValue metricMetricSource <> " IS NOT NULL"
         , "), aggregate_groups AS ("
         , "  SELECT"
         , "    entity_name,"
         , "    MAX(context_value) AS context_value,"
         ]
      <> renderMetadataAggregateSelectLines metricDisplayMetadata
      <> [
           "    " <> compileMetricAggregation metricFormulaValue <> " AS metric_value"
         , "  FROM season_rows"
         , "  GROUP BY entity_name"
         , ")"
         , "SELECT"
         , "  entity_name,"
         , "  context_value,"
         ]
      <> renderMetadataFinalSelectLines metricDisplayMetadata
      <> [
           "  metric_value"
         , "FROM aggregate_groups"
         , "ORDER BY entity_name ASC"
         ]
      <> limitClause metricQueryLimit
