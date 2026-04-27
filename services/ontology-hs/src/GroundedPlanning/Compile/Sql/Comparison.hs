{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Comparison (compileComparisonSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve

compileComparisonSql :: ResolvedMetricQuery -> Text
compileComparisonSql resolved =
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
        , factTableName = metricFactTableName
        , windowGames = metricWindowGames
        , linkedFiltersResolved = metricLinkedFilters
        } = resolved
      entityList =
        T.intercalate
          ", "
          (map (\entityValue -> T.pack (show (entityIdValue entityValue))) resolvedComparisonEntities)
   in T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricEntityId <> " AS entity_id,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_value,"
        , "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" metricPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
          <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
          <> [ "  WHERE " <> combineWhereClauses (renderColumnRefWithContext "f" "r" "c" metricEntityId <> " IN (" <> entityList <> ")" : renderLinkedFilterConditions "f" metricLinkedFilters)
        , ")"
        , "SELECT"
        , "  entity_id,"
        , "  entity_name,"
        , "  context_value,"
        , "  game_date,"
        , "  metric_value"
        , "FROM recent_rows"
        , "WHERE game_rank <= " <> T.pack (show metricWindowGames)
        , "ORDER BY entity_id ASC, game_date DESC"
        ]
