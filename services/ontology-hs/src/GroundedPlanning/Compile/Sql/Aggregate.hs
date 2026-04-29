{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Aggregate (compileAggregateSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve

-- Build SQL for grouped aggregate questions.
-- This uses ontology-resolved grouping columns instead of assuming every
-- aggregate has exactly one "entity_name" grouping axis.
compileAggregateSql :: ResolvedMetricQuery -> Text
compileAggregateSql resolved@ResolvedMetricQuery {seasonLabel = maybeSeasonLabel, seasonType = maybeSeasonType, windowGames = metricWindowGamesValue} =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue)
      | metricWindowGamesValue <= 0 ->
      compileSeasonAggregateSql resolved seasonLabelValue seasonTypeValue
    _ -> compileRecentAggregateSql resolved

compileRecentAggregateSql :: ResolvedMetricQuery -> Text
compileRecentAggregateSql resolved =
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
      , timeFilters = metricTimeFilters
      , groupingDimensions = metricGroupingDimensions
      , displayMetadata = metricDisplayMetadata
      , queryLimit = metricQueryLimit
      , rowPredicateResolved = metricRowPredicate
      , resultPredicateResolved = metricResultPredicate
      , displayMetricFormulas = metricDisplayMetricFormulas
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
      <> [ "    " <> renderAggregateEntityName metricGroupingDimensions metricDisplayName <> " AS entity_name,"
    , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
    , "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
    , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_source,"
    ]
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
      <> renderRowPredicateJoinClauses "f" metricRowPredicate
      <> baseWhereClause
      <> [ "), aggregate_groups AS ("
    , "  SELECT"
    ]
      <> renderGroupingAggregateSelectLines metricGroupingDimensions
      <> [ "    MIN(entity_name) AS entity_name,"
    , "    MAX(context_value) AS context_value,"
    ]
      <> renderMetadataAggregateSelectLines metricDisplayMetadata
      <> renderDisplayMetricAggregateSelectLines metricDisplayMetricFormulas
      <> renderResultPredicateAggregateSelectLines metricResultPredicate
      <> [ "    " <> compileMetricAggregation resolvedMetricFormulaValue <> " AS metric_value"
    , "  FROM recent_rows"
    ]
      <> gameRankWhereClause
      <> [ "  GROUP BY " <> renderGroupingKeys metricGroupingDimensions
    , ")"
    , "SELECT"
    , "  " <> primaryGroupingKey metricGroupingDimensions <> " AS entity_name,"
    , "  context_value,"
    ]
      <> renderGroupingFinalSelectLines metricGroupingDimensions
      <> renderMetadataFinalSelectLines metricDisplayMetadata
      <> renderResultPredicateFinalSelectLines metricResultPredicate
      <> renderDisplayMetricFinalSelectLines metricDisplayMetricFormulas
      <> [ "  metric_value"
    , "FROM aggregate_groups"
    ]
      <> resultFilterWhereClause
      <> [ "ORDER BY " <> renderGroupingOrder metricGroupingDimensions ]
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
      , rowPredicateResolved = metricRowPredicate
      , resultPredicateResolved = metricResultPredicate
      , groupingDimensions = metricGroupingDimensions
      , displayMetadata = metricDisplayMetadata
      , displayMetricFormulas = metricDisplayMetricFormulas
      } = resolved
   in
  T.unlines $
    [ "WITH season_rows AS ("
    , "  SELECT"
    ]
      <> renderGroupingSourceSelectLines metricGroupingDimensions
      <> [ "    " <> renderAggregateEntityName metricGroupingDimensions metricDisplayName <> " AS entity_name,"
    , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
    , "    " <> renderMetricValue metricMetricSource <> " AS metric_source,"
    ]
      <> renderMetadataSourceSelectLines "f" "r" "c" metricDisplayMetadata
      <> renderDisplayMetricSourceSelectLines "f" metricDisplayMetricFormulas
      <> renderResultPredicateSourceSelectLines "f" metricResultPredicate
      <> [ "    1 AS __metadata_row"
    , "  FROM " <> metricFactTableName <> " f"
    ]
      <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
      <> renderGroupingJoinClauses metricGroupingDimensions
      <> renderRowPredicateJoinClauses "f" metricRowPredicate
      <> [ "  WHERE " <> combineWhereClauses (seasonWhereClause seasonLabelValue seasonTypeValue : renderRowPredicateConditions "f" metricRowPredicate)
         , "    AND " <> renderMetricValue metricMetricSource <> " IS NOT NULL"
         , "), aggregate_groups AS ("
         , "  SELECT"
         ]
      <> renderGroupingAggregateSelectLines metricGroupingDimensions
      <> [
           "    MIN(entity_name) AS entity_name,"
         , "    MAX(context_value) AS context_value,"
         ]
      <> renderMetadataAggregateSelectLines metricDisplayMetadata
      <> renderDisplayMetricAggregateSelectLines metricDisplayMetricFormulas
      <> renderResultPredicateAggregateSelectLines metricResultPredicate
      <> [
           "    " <> compileMetricAggregation metricFormulaValue <> " AS metric_value"
         , "  FROM season_rows"
         , "  GROUP BY " <> renderGroupingKeys metricGroupingDimensions
         , ")"
         , "SELECT"
         , "  " <> primaryGroupingKey metricGroupingDimensions <> " AS entity_name,"
         , "  context_value,"
         ]
      <> renderGroupingFinalSelectLines metricGroupingDimensions
      <> renderMetadataFinalSelectLines metricDisplayMetadata
      <> renderResultPredicateFinalSelectLines metricResultPredicate
      <> renderDisplayMetricFinalSelectLines metricDisplayMetricFormulas
      <> [
           "  metric_value"
         , "FROM aggregate_groups"
         ]
      <> (case renderResultPredicateConditions metricResultPredicate of
            [] -> []
            conditions -> ["WHERE " <> combineWhereClauses conditions])
      <> [ "ORDER BY " <> renderGroupingOrder metricGroupingDimensions ]
      <> limitClause metricQueryLimit

renderAggregateEntityName :: [ResolvedGroupingDimension] -> ColumnRef -> Text
renderAggregateEntityName groupingDimensions fallbackColumnRef =
  case groupingDimensions of
    groupingDimension : _ -> renderGroupingSource 1 groupingDimension
    [] -> renderColumnRefWithContext "f" "r" "c" fallbackColumnRef
