{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Object (compileObjectSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve

-- Build SQL for object-row questions.
-- Similar to ranking SQL, but the final result shape is object rows rather than
-- ranked rows with a rank column.
compileObjectSql :: ResolvedObjectQuery -> Text
compileObjectSql resolved@ResolvedObjectQuery {seasonLabel = maybeSeasonLabel, seasonType = maybeSeasonType} =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue) ->
      compileSeasonObjectSql resolved seasonLabelValue seasonTypeValue
    _ ->
      let
        ResolvedObjectQuery
          { partitionKey = objectPartitionKey
          , entityId = objectEntityId
          , rowPath = objectRowPath
          , contextPath = objectContextPath
          , displayName = objectDisplayName
          , contextValue = objectContextValue
          , gameDate = objectGameDate
          , metricSource = objectMetricSource
          , factTableName = objectFactTableName
          , metricFormula = objectMetricFormula
          , windowGames = objectWindowGames
          , queryLimit = objectQueryLimit
          , linkedFiltersResolved = objectLinkedFilters
          , objectOrderDirection = objectOrderDirectionValue
          } = resolved
       in
      T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" objectEntityId <> " AS entity_id,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" objectDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" objectContextValue <> " AS context_value,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" objectGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" objectMetricSource <> " AS metric_source,"
        , "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" objectPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" objectGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> objectFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" objectRowPath
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" objectContextPath
          <> renderLinkedFilterJoinClauses "f" objectLinkedFilters
          <> renderLinkedFilterWhereClause "f" objectLinkedFilters
          <> [ "), entity_values AS ("
        , "  SELECT"
        , "    entity_id,"
        , "    arg_max(entity_name, game_date) AS entity_name,"
        , "    arg_max(context_value, game_date) AS context_value,"
        , "    " <> compileMetricAggregation objectMetricFormula <> " AS metric_value"
        , "  FROM recent_rows"
        , "  WHERE game_rank <= " <> T.pack (show objectWindowGames)
        , "  GROUP BY entity_id"
        , ")"
        , "SELECT"
        , "  entity_id,"
        , "  entity_name,"
        , "  context_value,"
        , "  metric_value"
        , "FROM entity_values"
        , "ORDER BY metric_value " <> objectOrderDirectionValue <> ", entity_name ASC"
        ]
          <> limitClause objectQueryLimit

-- Special SQL path for season-level object-row questions.
compileSeasonObjectSql :: ResolvedObjectQuery -> Text -> Text -> Text
compileSeasonObjectSql resolved seasonLabelValue seasonTypeValue =
  let
    ResolvedObjectQuery
      { entityId = objectEntityId
      , displayName = objectDisplayName
      , contextValue = objectContextValue
      , metricSource = objectMetricSource
      , factTableName = objectFactTableName
      , rowPath = objectRowPath
      , contextPath = objectContextPath
      , queryLimit = objectQueryLimit
      , linkedFiltersResolved = objectLinkedFilters
      , objectOrderDirection = objectOrderDirectionValue
      } = resolved
   in
  T.unlines $
    [ "SELECT"
    , "  " <> renderColumnRefWithContext "f" "r" "c" objectEntityId <> " AS entity_id,"
    , "  " <> renderColumnRefWithContext "f" "r" "c" objectDisplayName <> " AS entity_name,"
    , "  " <> renderMaybeColumnRef "f" "r" "c" objectContextValue <> " AS context_value,"
    , "  " <> renderMetricValue objectMetricSource <> " AS metric_value"
    , "FROM " <> objectFactTableName <> " f"
    ]
      <> renderPathJoinClauses "JOIN" "f" "r" "rp" objectRowPath
      <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" objectContextPath
      <> renderLinkedFilterJoinClauses "f" objectLinkedFilters
      <> [ "WHERE " <> combineWhereClauses (seasonWhereClause seasonLabelValue seasonTypeValue : renderLinkedFilterConditions "f" objectLinkedFilters)
         , "ORDER BY metric_value " <> objectOrderDirectionValue <> ", entity_name ASC"
         ]
      <> limitClause objectQueryLimit
