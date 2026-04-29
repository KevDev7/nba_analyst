{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Comparison (compileComparisonSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve

compileComparisonSql :: ResolvedMetricQuery -> Text
compileComparisonSql resolved@ResolvedMetricQuery {timeFilterKind = comparisonTimeFilterKind} =
  if comparisonTimeFilterKind == "exact_season+season_type"
    then compileSeasonComparisonSql resolved
    else compileRecentComparisonSql resolved

compileRecentComparisonSql :: ResolvedMetricQuery -> Text
compileRecentComparisonSql resolved =
  let
      ResolvedMetricQuery
        { comparisonEntities = resolvedComparisonEntities
        , entityId = metricEntityId
        , partitionKey = metricPartitionKey
        , rowPath = metricRowPath
        , contextPath = metricContextPath
        , displayName = metricDisplayName
        , contextValue = metricContextValue
        , gameDate = metricGameDate
        , metricSource = metricMetricSource
        , metricTimeBucketExpression = maybeTimeBucketExpression
        , factTableName = metricFactTableName
        , windowGames = metricWindowGames
        , timeFilters = metricTimeFilters
        , rowPredicateResolved = metricRowPredicate
        , groupingDimensions = metricGroupingDimensions
        } = resolved
      entityList =
        T.intercalate
          ", "
          (map (\entityValue -> T.pack (show (entityIdValue entityValue))) resolvedComparisonEntities)
      baseWhereConditions =
        renderColumnRefWithContext "f" "r" "c" metricEntityId <> " IN (" <> entityList <> ")"
          : renderGameDateFilterConditions metricFactTableName "f" metricTimeFilters
          <> renderRowPredicateConditions "f" metricRowPredicate
      gameRankWhereConditions =
        if metricWindowGames > 0
          then ["game_rank <= " <> T.pack (show metricWindowGames)]
          else []
      timeBucketSourceSelectLines =
        case maybeTimeBucketExpression of
          Just bucketExpression -> ["    " <> renderFactExpression "f" bucketExpression <> " AS time_bucket,"]
          Nothing -> []
      timeBucketFinalSelectLines =
        case maybeTimeBucketExpression of
          Just _ -> ["  time_bucket,"]
          Nothing -> []
      timeBucketOrder =
        case maybeTimeBucketExpression of
          Just _ -> ", time_bucket ASC"
          Nothing -> ""
      groupingOrder =
        case renderGroupingOrder metricGroupingDimensions of
          "" -> ""
          orderValue -> ", " <> orderValue
   in T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricEntityId <> " AS entity_id,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
        ]
          <> timeBucketSourceSelectLines
          <> renderGroupingSourceSelectLines metricGroupingDimensions
          <> [ "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_value,"
        , "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" metricPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
          <> renderGroupingJoinClauses metricGroupingDimensions
          <> renderRowPredicateJoinClauses "f" metricRowPredicate
          <> [ "  WHERE " <> combineWhereClauses baseWhereConditions
        , ")"
        , "SELECT"
        , "  entity_id,"
        , "  entity_name,"
        , "  context_value,"
        ]
          <> timeBucketFinalSelectLines
          <> renderGroupingFinalSelectLines metricGroupingDimensions
          <> [ "  game_date,"
        , "  metric_value"
        , "FROM recent_rows"
        ]
          <> renderWhereLines "" gameRankWhereConditions
          <> [ "ORDER BY entity_id ASC" <> timeBucketOrder <> groupingOrder <> ", game_date DESC" ]

renderWhereLines :: Text -> [Text] -> [Text]
renderWhereLines prefix conditions =
  case conditions of
    [] -> []
    _ -> [prefix <> "WHERE " <> combineWhereClauses conditions]

compileSeasonComparisonSql :: ResolvedMetricQuery -> Text
compileSeasonComparisonSql resolved =
  let
      ResolvedMetricQuery
        { comparisonEntities = resolvedComparisonEntities
        , entityId = metricEntityId
        , rowPath = metricRowPath
        , contextPath = metricContextPath
        , displayName = metricDisplayName
        , contextValue = metricContextValue
        , metricSource = metricMetricSource
        , metricTimeBucketExpression = maybeTimeBucketExpression
        , factTableName = metricFactTableName
        , seasonLabel = metricSeasonLabel
        , seasonType = metricSeasonType
        , rowPredicateResolved = metricRowPredicate
        , displayMetadata = metricDisplayMetadata
        , groupingDimensions = metricGroupingDimensions
        } = resolved
      entityList =
        T.intercalate
          ", "
          (map (\entityValue -> T.pack (show (entityIdValue entityValue))) resolvedComparisonEntities)
      seasonWhereConditions =
        renderColumnRefWithContext "f" "r" "c" metricEntityId <> " IN (" <> entityList <> ")"
          : renderSeasonFilterConditions "f" metricSeasonLabel metricSeasonType
          <> renderRowPredicateConditions "f" metricRowPredicate
      gamesPlayedSelectLines =
        case
          [ "    " <> renderColumnRefWithContext "f" "r" "c" sourceColumn <> " AS games_played,"
          | metadataValue <- metricDisplayMetadata
          , metadataKey metadataValue == "games_played"
          , Just sourceColumn <- [metadataSource metadataValue]
          ]
          of
          [] -> ["    NULL AS games_played,"]
          values -> values
      timeBucketSourceSelectLines =
        case maybeTimeBucketExpression of
          Just bucketExpression -> ["    " <> renderFactExpression "f" bucketExpression <> " AS time_bucket,"]
          Nothing -> []
      timeBucketFinalSelectLines =
        case maybeTimeBucketExpression of
          Just _ -> ["  time_bucket,"]
          Nothing -> []
      timeBucketOrder =
        case maybeTimeBucketExpression of
          Just _ -> ", time_bucket ASC"
          Nothing -> ""
      groupingOrder =
        case renderGroupingOrder metricGroupingDimensions of
          "" -> ""
          orderValue -> ", " <> orderValue
   in T.unlines $
        [ "WITH season_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricEntityId <> " AS entity_id,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
        ]
          <> timeBucketSourceSelectLines
          <> renderGroupingSourceSelectLines metricGroupingDimensions
          <> gamesPlayedSelectLines
          <> [ "    NULL AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_value"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
          <> renderGroupingJoinClauses metricGroupingDimensions
          <> renderRowPredicateJoinClauses "f" metricRowPredicate
          <> [ "  WHERE " <> combineWhereClauses seasonWhereConditions
        , ")"
        , "SELECT"
        , "  entity_id,"
        , "  entity_name,"
        , "  context_value,"
        ]
          <> timeBucketFinalSelectLines
          <> renderGroupingFinalSelectLines metricGroupingDimensions
          <> [ "  games_played,"
        , "  game_date,"
        , "  metric_value"
        , "FROM season_rows"
        , "ORDER BY entity_id ASC" <> timeBucketOrder <> groupingOrder
        ]
