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
      , timeBucketExpression = trendTimeBucketExpression
      , metricSource = trendMetricSource
      , metricFormula = trendMetricFormula
      , trendFilters = trendFilterValues
      , trendRowPredicateResolved = trendRowPredicate
      , trendResultPredicateResolved = trendResultPredicate
      , trendGroupingDimensions = groupingDimensions
      } = resolved
    trendWhereConditions = renderTrendFilterConditions trendFactTableName trendFilterValues <> renderRowPredicateConditions "f" trendRowPredicate
    resultFilterSourceLines = stripLastTrailingComma (renderResultPredicateSourceSelectLines "f" trendResultPredicate)
    metricSourceLine =
      "    " <> renderColumnRefWithContext "f" "s" "c" trendMetricSource <> " AS metric_source"
        <> if null resultFilterSourceLines then "" else ","
    resultFilterWhereClause =
      case renderResultPredicateConditions trendResultPredicate of
        [] -> []
        conditions -> ["WHERE " <> combineWhereClauses conditions]
   in
  T.unlines $
    [ "WITH filtered_rows AS ("
    , "  SELECT"
    , "    " <> renderFactExpression "f" trendTimeBucketExpression <> " AS time_bucket,"
    ]
      <> renderGroupingSourceSelectLines groupingDimensions
      <> [ "    " <> renderTrendSeriesName groupingDimensions <> " AS series_name,"
      , metricSourceLine
     ]
      <> resultFilterSourceLines
      <> [ "  FROM " <> trendFactTableName <> " f" ]
      <> renderGroupingJoinClauses groupingDimensions
      <> renderRowPredicateJoinClauses "f" trendRowPredicate
      <> (if null trendWhereConditions then [] else ["  WHERE " <> combineWhereClauses trendWhereConditions])
      <> [ "), aggregated_series AS ("
         , "  SELECT"
         , "    time_bucket,"
         ]
      <> renderGroupingAggregateSelectLines groupingDimensions
      <> [ "    MIN(series_name) AS series_name," ]
      <> renderResultPredicateAggregateSelectLines trendResultPredicate
      <> [ "    " <> compileMetricAggregation trendMetricFormula <> " AS metric_value"
         , "  FROM filtered_rows"
         , "  GROUP BY " <> renderTrendGroupKeys groupingDimensions
         , ")"
         , "SELECT"
         , "  time_bucket,"
         , "  series_name,"
         ]
      <> renderGroupingFinalSelectLines groupingDimensions
      <> [ "  metric_value"
         , "FROM aggregated_series"
         ]
      <> resultFilterWhereClause
      <> [ "ORDER BY " <> renderTrendOrder groupingDimensions ]

stripLastTrailingComma :: [Text] -> [Text]
stripLastTrailingComma sourceLines =
  case reverse sourceLines of
    [] -> []
    lastLine : earlierLines ->
      reverse earlierLines
        <> [ case T.stripSuffix "," lastLine of
               Just strippedLine -> strippedLine
               Nothing -> lastLine
           ]

renderTrendSeriesName :: [ResolvedGroupingDimension] -> Text
renderTrendSeriesName groupingDimensions =
  case groupingDimensions of
    groupingDimension : _ -> renderGroupingSource 1 groupingDimension
    [] -> "NULL"

renderTrendGroupKeys :: [ResolvedGroupingDimension] -> Text
renderTrendGroupKeys groupingDimensions =
  case renderGroupingKeys groupingDimensions of
    "" -> "time_bucket, series_name"
    groupingKeys -> "time_bucket, " <> groupingKeys

renderTrendOrder :: [ResolvedGroupingDimension] -> Text
renderTrendOrder groupingDimensions =
  case renderGroupingOrder groupingDimensions of
    "" -> "time_bucket ASC, series_name ASC"
    groupingOrder -> "time_bucket ASC, " <> groupingOrder
