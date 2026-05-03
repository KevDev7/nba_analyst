{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Ranking (compileRankingSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
  ( compileMetricAggregation
  , renderMetricFormulaDirectValue
  , renderMetricFormulaSourceSelectLines
  , renderGameDateFilterConditions
  , renderMaybePathJoinClauses
  , renderPathJoinClauses
  , renderResultPredicateConditions
  , renderRowPredicateConditions
  , renderRowPredicateJoinClauses
  , seasonWhereClause
  )
import GroundedPlanning.Compile.Sql.Common.Primitives
  ( combineWhereClauses
  , limitClause
  , renderColumnRefWithContext
  , renderMaybeColumnRef
  )
import GroundedPlanning.Compile.Sql.Grouping
  ( primaryGroupingKey
  , renderGroupingAggregateSelectLines
  , renderGroupingFinalSelectLines
  , renderGroupingJoinClauses
  , renderGroupingKeys
  , renderGroupingSource
  , renderGroupingSourceSelectLines
  )
import GroundedPlanning.Compile.Sql.Projection
  ( renderDisplayMetricAggregateSelectLines
  , renderDisplayMetricDirectSelectLines
  , renderDisplayMetricFinalSelectLines
  , renderDisplayMetricSourceSelectLines
  , renderMetadataAggregateSelectLines
  , renderMetadataDirectSelectLines
  , renderMetadataFinalSelectLines
  , renderMetadataSourceSelectLines
  , renderResultPredicateAggregateSelectLines
  , renderResultPredicateDirectSelectLines
  , renderResultPredicateFinalSelectLines
  , renderResultPredicateSourceSelectLines
  )
import GroundedPlanning.Resolve

-- Build SQL for ranking/top-N style questions.
-- There are two variants:
-- 1. season-scoped queries that can read directly from season-level rows
-- 2. recent-games queries that must rank rows, trim to the last N games, then aggregate
compileRankingSql :: ResolvedMetricQuery -> Text
compileRankingSql resolved@ResolvedMetricQuery {seasonLabel = maybeSeasonLabel, seasonType = maybeSeasonType, windowGames = metricWindowGamesValue} =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue)
      | metricWindowGamesValue <= 0 ->
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
          , timeFilters = metricTimeFilters
          , displayMetadata = metricDisplayMetadata
          , queryLimit = metricQueryLimit
          , rowPredicateResolved = metricRowPredicate
          , resultPredicateResolved = metricResultPredicate
          , metricOrderDirection = metricOrderDirectionValue
          , displayMetricFormulas = metricDisplayMetricFormulas
          , groupingDimensions = metricGroupingDimensions
          } = resolved
        baseWhereConditions =
          renderGameDateFilterConditions metricFactTableName "f" metricTimeFilters
            <> renderRowPredicateConditions "f" metricRowPredicate
        baseWhereClause =
          case baseWhereConditions of
            [] -> []
            conditions -> ["  WHERE " <> combineWhereClauses conditions]
        resultFilterWhereClause =
          case renderResultPredicateConditions metricResultPredicate of
            [] -> []
            conditions -> ["WHERE " <> combineWhereClauses conditions]
        gameRankWhereClause =
          if metricWindowGames > 0
            then ["  WHERE game_rank <= " <> T.pack (show metricWindowGames)]
            else []
       in
      T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        ]
          <> renderGroupingSourceSelectLines metricGroupingDimensions
          <> [ "    " <> renderColumnRefWithContext "f" "r" "c" metricEntityId <> " AS entity_id,"
        , "    " <> renderRankingEntityName metricGroupingDimensions metricDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_source,"
        ]
          <> renderMetricFormulaSourceSelectLines "f" resolvedMetricFormulaValue
          <> renderMetadataSourceSelectLines "f" "r" "c" metricDisplayMetadata
          <> renderDisplayMetricSourceSelectLines "f" metricDisplayMetricFormulas
          <> renderResultPredicateSourceSelectLines "f" metricResultPredicate
          <> [ "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" metricPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderGroupingJoinClauses metricGroupingDimensions
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
          <> renderRowPredicateJoinClauses "f" metricRowPredicate
          <> baseWhereClause
          <> [ "), ranked_entities AS ("
        , "  SELECT"
        , "    entity_id,"
        ]
          <> renderGroupingAggregateSelectLines metricGroupingDimensions
          <> [ "    arg_max(entity_name, game_date) AS entity_name,"
        , "    arg_max(context_value, game_date) AS context_value,"
        ]
          <> renderMetadataAggregateSelectLines metricDisplayMetadata
          <> renderDisplayMetricAggregateSelectLines metricDisplayMetricFormulas
          <> renderResultPredicateAggregateSelectLines metricResultPredicate
          <> [ "    " <> compileMetricAggregation resolvedMetricFormulaValue <> " AS metric_value"
        , "  FROM recent_rows"
       ]
          <> gameRankWhereClause
          <> [ "  GROUP BY " <> renderRankingGroupKeys metricGroupingDimensions
        , ")"
        , "SELECT"
        , "  ROW_NUMBER() OVER (ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC) AS rank,"
        , "  " <> primaryGroupingKey metricGroupingDimensions <> " AS entity_name,"
        , "  context_value,"
        ]
          <> renderGroupingFinalSelectLines metricGroupingDimensions
          <> renderMetadataFinalSelectLines metricDisplayMetadata
          <> renderResultPredicateFinalSelectLines metricResultPredicate
          <> renderDisplayMetricFinalSelectLines metricDisplayMetricFormulas
          <> [ "  metric_value"
        , "FROM ranked_entities"
        ]
          <> resultFilterWhereClause
          <> [ "ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC" ]
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
      , rowPredicateResolved = metricRowPredicate
      , resultPredicateResolved = metricResultPredicate
      , metricFormula = resolvedMetricFormulaValue
      , metricOrderDirection = metricOrderDirectionValue
      , displayMetadata = metricDisplayMetadata
      , displayMetricFormulas = metricDisplayMetricFormulas
      , groupingDimensions = metricGroupingDimensions
      } = resolved
   in
  T.unlines $
    [ "WITH season_ranked_entities AS ("
    , "  SELECT"
    ]
      <> renderGroupingSourceSelectLines metricGroupingDimensions
      <> [ "    " <> renderRankingEntityName metricGroupingDimensions metricDisplayName <> " AS entity_name,"
    , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
    ]
      <> renderMetricFormulaSourceSelectLines "f" resolvedMetricFormulaValue
      <> renderMetadataDirectSelectLines "f" "r" "c" metricDisplayMetadata
      <> renderDisplayMetricDirectSelectLines "f" metricDisplayMetricFormulas
      <> renderResultPredicateDirectSelectLines "f" metricResultPredicate
      <> [ "    " <> renderMetricFormulaDirectValue "f" metricMetricSource resolvedMetricFormulaValue <> " AS metric_value"
    , "  FROM " <> metricFactTableName <> " f"
    ]
      <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
      <> renderGroupingJoinClauses metricGroupingDimensions
      <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
      <> renderRowPredicateJoinClauses "f" metricRowPredicate
      <> [ "  WHERE " <> combineWhereClauses (seasonWhereClause seasonLabelValue seasonTypeValue : renderRowPredicateConditions "f" metricRowPredicate)
         , "    AND " <> renderMetricFormulaDirectValue "f" metricMetricSource resolvedMetricFormulaValue <> " IS NOT NULL"
         , ")"
         , "SELECT"
    , "  ROW_NUMBER() OVER (ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC) AS rank,"
    , "  " <> primaryGroupingKey metricGroupingDimensions <> " AS entity_name,"
    , "  context_value,"
         ]
      <> renderGroupingFinalSelectLines metricGroupingDimensions
      <> renderMetadataFinalSelectLines metricDisplayMetadata
      <> renderResultPredicateFinalSelectLines metricResultPredicate
      <> renderDisplayMetricFinalSelectLines metricDisplayMetricFormulas
      <> [ "  metric_value"
         , "FROM season_ranked_entities"
         ]
      <> (case renderResultPredicateConditions metricResultPredicate of
            [] -> []
            conditions -> ["WHERE " <> combineWhereClauses conditions])
      <> [
           "ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC"
         ]
      <> limitClause metricQueryLimit

renderRankingEntityName :: [ResolvedGroupingDimension] -> ColumnRef -> Text
renderRankingEntityName groupingDimensions fallbackColumnRef =
  case groupingDimensions of
    groupingDimension : _ -> renderGroupingSource 1 groupingDimension
    [] -> renderColumnRefWithContext "f" "r" "c" fallbackColumnRef

renderRankingGroupKeys :: [ResolvedGroupingDimension] -> Text
renderRankingGroupKeys groupingDimensions =
  case renderGroupingKeys groupingDimensions of
    "" -> "entity_id"
    groupingKeys -> "entity_id, " <> groupingKeys
