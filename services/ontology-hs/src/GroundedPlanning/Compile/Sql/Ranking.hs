{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Ranking (compileRankingSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve

-- Build SQL for ranking/top-N style questions.
-- There are two variants:
-- 1. season-scoped queries that can read directly from season-level rows
-- 2. recent-games queries that must rank rows, trim to the last N games, then aggregate
compileRankingSql :: ResolvedMetricQuery -> Text
compileRankingSql resolved@ResolvedMetricQuery {seasonLabel = maybeSeasonLabel, seasonType = maybeSeasonType} =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue) ->
      compileSeasonRankingSql resolved seasonLabelValue seasonTypeValue
    _ ->
      let
        ResolvedMetricQuery
          { partitionKey = metricPartitionKey
          , entityId = metricEntityId
          , rowPath = metricRowPath
          , contextPath = metricContextPath
          , displayName = metricDisplayName
          , contextValue = metricContextValue
          , gameDate = metricGameDate
          , metricSource = metricMetricSource
          , factTableName = metricFactTableName
          , metricFormula = resolvedMetricFormulaValue
          , windowGames = metricWindowGames
          , queryLimit = metricQueryLimit
          , linkedFiltersResolved = metricLinkedFilters
          , metricOrderDirection = metricOrderDirectionValue
          } = resolved
       in
      T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricEntityId <> " AS entity_id,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_source,"
        , "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" metricPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
          <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
          <> renderLinkedFilterWhereClause "f" metricLinkedFilters
          <> [ "), ranked_entities AS ("
        , "  SELECT"
        , "    entity_id,"
        , "    arg_max(entity_name, game_date) AS entity_name,"
        , "    arg_max(context_value, game_date) AS context_value,"
        , "    " <> compileMetricAggregation resolvedMetricFormulaValue <> " AS metric_value"
        , "  FROM recent_rows"
        , "  WHERE game_rank <= " <> T.pack (show metricWindowGames)
        , "  GROUP BY entity_id"
        , ")"
        , "SELECT"
        , "  ROW_NUMBER() OVER (ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC) AS rank,"
        , "  entity_name,"
        , "  context_value,"
        , "  metric_value"
        , "FROM ranked_entities"
        , "ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC"
        ]
          <> limitClause metricQueryLimit

-- Special SQL path for season-level ranking questions.
-- These do not need "last N games" logic because the fact surface is already
-- season-scoped.
compileSeasonRankingSql :: ResolvedMetricQuery -> Text -> Text -> Text
compileSeasonRankingSql resolved seasonLabelValue seasonTypeValue =
  let
    ResolvedMetricQuery
      { displayName = metricDisplayName
      , contextValue = metricContextValue
      , metricSource = metricMetricSource
      , factTableName = metricFactTableName
      , rowPath = metricRowPath
      , contextPath = metricContextPath
      , queryLimit = metricQueryLimit
      , linkedFiltersResolved = metricLinkedFilters
      , metricOrderDirection = metricOrderDirectionValue
      } = resolved
   in
  T.unlines $
    [ "WITH season_ranked_entities AS ("
    , "  SELECT"
    , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
    , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
    , "    " <> renderMetricValue metricMetricSource <> " AS metric_value"
    , "  FROM " <> metricFactTableName <> " f"
    ]
      <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
      <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
      <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
      <> [ "  WHERE " <> combineWhereClauses (seasonWhereClause seasonLabelValue seasonTypeValue : renderLinkedFilterConditions "f" metricLinkedFilters)
         , "    AND " <> renderMetricValue metricMetricSource <> " IS NOT NULL"
         , ")"
         , "SELECT"
    , "  ROW_NUMBER() OVER (ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC) AS rank,"
         , "  entity_name,"
         , "  context_value,"
         , "  metric_value"
         , "FROM season_ranked_entities"
         , "ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC"
         ]
      <> limitClause metricQueryLimit
