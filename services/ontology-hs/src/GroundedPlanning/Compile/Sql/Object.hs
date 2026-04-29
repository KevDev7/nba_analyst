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
compileObjectSql resolved@ResolvedObjectQuery {seasonLabel = maybeSeasonLabel, seasonType = maybeSeasonType, windowGames = objectWindowGamesValue} =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue)
      | objectWindowGamesValue <= 0 ->
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
          , timeFilters = objectTimeFilters
          , displayMetadata = objectDisplayMetadata
          , queryLimit = objectQueryLimit
          , objectRowPredicateResolved = objectRowPredicate
          , objectResultPredicateResolved = objectResultPredicate
          , objectOrderDirection = objectOrderDirectionValue
          , displayMetricFormulas = objectDisplayMetricFormulas
          } = resolved
        baseWhereConditions =
          renderGameDateFilterConditions objectFactTableName "f" objectTimeFilters
            <> renderRowPredicateConditions "f" objectRowPredicate
        baseWhereClause =
          case baseWhereConditions of
            [] -> []
            conditions -> ["  WHERE " <> combineWhereClauses conditions]
        resultFilterWhereClause =
          case renderResultPredicateConditions objectResultPredicate of
            [] -> []
            conditions -> ["WHERE " <> combineWhereClauses conditions]
        gameRankWhereClause =
          if objectWindowGames > 0
            then ["  WHERE game_rank <= " <> T.pack (show objectWindowGames)]
            else []
       in
      T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" objectEntityId <> " AS entity_id,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" objectDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" objectContextValue <> " AS context_value,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" objectGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" objectMetricSource <> " AS metric_source,"
        ]
          <> renderMetadataSourceSelectLines "f" "r" "c" objectDisplayMetadata
          <> renderDisplayMetricSourceSelectLines "f" objectDisplayMetricFormulas
          <> renderResultPredicateSourceSelectLines "f" objectResultPredicate
          <> [ "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" objectPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" objectGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> objectFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" objectRowPath
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" objectContextPath
          <> renderRowPredicateJoinClauses "f" objectRowPredicate
          <> baseWhereClause
          <> [ "), entity_values AS ("
        , "  SELECT"
        , "    entity_id,"
        , "    arg_max(entity_name, game_date) AS entity_name,"
        , "    arg_max(context_value, game_date) AS context_value,"
        ]
          <> renderMetadataAggregateSelectLines objectDisplayMetadata
          <> renderDisplayMetricAggregateSelectLines objectDisplayMetricFormulas
          <> renderResultPredicateAggregateSelectLines objectResultPredicate
          <> [ "    " <> compileMetricAggregation objectMetricFormula <> " AS metric_value"
        , "  FROM recent_rows"
        ]
          <> gameRankWhereClause
          <> [ "  GROUP BY entity_id"
        , ")"
        , "SELECT"
        , "  entity_id,"
        , "  entity_name,"
        , "  context_value,"
        ]
          <> renderMetadataFinalSelectLines objectDisplayMetadata
          <> renderResultPredicateFinalSelectLines objectResultPredicate
          <> renderDisplayMetricFinalSelectLines objectDisplayMetricFormulas
          <> [ "  metric_value"
        , "FROM entity_values"
        ]
          <> resultFilterWhereClause
          <> [ "ORDER BY metric_value " <> objectOrderDirectionValue <> ", entity_name ASC" ]
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
      , objectRowPredicateResolved = objectRowPredicate
      , objectResultPredicateResolved = objectResultPredicate
      , objectOrderDirection = objectOrderDirectionValue
      , displayMetadata = objectDisplayMetadata
      , displayMetricFormulas = objectDisplayMetricFormulas
      } = resolved
   in
  T.unlines $
    [ "WITH season_entity_values AS ("
    , "  SELECT"
    , "    " <> renderColumnRefWithContext "f" "r" "c" objectEntityId <> " AS entity_id,"
    , "    " <> renderColumnRefWithContext "f" "r" "c" objectDisplayName <> " AS entity_name,"
    , "    " <> renderMaybeColumnRef "f" "r" "c" objectContextValue <> " AS context_value,"
    ]
      <> renderMetadataDirectSelectLines "f" "r" "c" objectDisplayMetadata
      <> renderDisplayMetricDirectSelectLines "f" objectDisplayMetricFormulas
      <> renderResultPredicateDirectSelectLines "f" objectResultPredicate
      <> [ "    " <> renderMetricValue objectMetricSource <> " AS metric_value"
    , "  FROM " <> objectFactTableName <> " f"
    ]
      <> renderPathJoinClauses "JOIN" "f" "r" "rp" objectRowPath
      <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" objectContextPath
      <> renderRowPredicateJoinClauses "f" objectRowPredicate
      <> [ "WHERE " <> combineWhereClauses (seasonWhereClause seasonLabelValue seasonTypeValue : renderRowPredicateConditions "f" objectRowPredicate)
         , ")"
         , "SELECT"
         , "  entity_id,"
         , "  entity_name,"
         , "  context_value,"
         ]
      <> renderMetadataFinalSelectLines objectDisplayMetadata
      <> renderResultPredicateFinalSelectLines objectResultPredicate
      <> renderDisplayMetricFinalSelectLines objectDisplayMetricFormulas
      <> [ "  metric_value"
         , "FROM season_entity_values"
         ]
      <> (case renderResultPredicateConditions objectResultPredicate of
            [] -> []
            conditions -> ["WHERE " <> combineWhereClauses conditions])
      <> [ "ORDER BY metric_value " <> objectOrderDirectionValue <> ", entity_name ASC" ]
      <> limitClause objectQueryLimit
