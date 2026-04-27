{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Trend (compileTrendSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve

-- Build SQL for trend/time-series questions.
-- This groups rows into time buckets and aggregates each bucket, optionally with
-- a business grouping series like player or team.
compileTrendSql :: ResolvedTrendQuery -> Text
compileTrendSql resolved =
  let
    ResolvedTrendQuery
      { factTableName = trendFactTableName
      , seriesPath = trendSeriesPath
      , seriesName = trendSeriesName
      , timeBucketExpression = trendTimeBucketExpression
      , metricSource = trendMetricSource
      , metricFormula = trendMetricFormula
      , trendFilters = trendFilterValues
      , linkedFiltersResolved = trendLinkedFilters
      } = resolved
    trendWhereConditions = renderTrendFilterConditions trendFactTableName trendFilterValues <> renderLinkedFilterConditions "f" trendLinkedFilters
   in
  T.unlines $
    [ "WITH filtered_rows AS ("
    , "  SELECT"
    , "    " <> renderFactExpression "f" trendTimeBucketExpression <> " AS time_bucket,"
    , "    " <> renderMaybeColumnRef "f" "s" "c" trendSeriesName <> " AS series_name,"
    , "    " <> renderColumnRefWithContext "f" "s" "c" trendMetricSource <> " AS metric_source"
    , "  FROM " <> trendFactTableName <> " f"
    ]
      <> renderMaybePathJoinClauses "JOIN" "f" "s" "sp" trendSeriesPath
      <> renderLinkedFilterJoinClauses "f" trendLinkedFilters
      <> (if null trendWhereConditions then [] else ["  WHERE " <> combineWhereClauses trendWhereConditions])
      <> [ "), aggregated_series AS ("
         , "  SELECT"
         , "    time_bucket,"
         , "    series_name,"
         , "    " <> compileMetricAggregation trendMetricFormula <> " AS metric_value"
         , "  FROM filtered_rows"
         , "  GROUP BY time_bucket, series_name"
         , ")"
         , "SELECT"
         , "  time_bucket,"
         , "  series_name,"
         , "  metric_value"
         , "FROM aggregated_series"
         , "ORDER BY time_bucket ASC, series_name ASC"
         ]
