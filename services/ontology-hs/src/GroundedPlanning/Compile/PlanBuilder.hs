-- Purpose:
-- Build runtime execution-plan envelopes from resolved semantic queries.
--
-- SQL text is delegated to GroundedPlanning.Compile.Sql.* modules.

{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.PlanBuilder (compileExecutionPlan) where

import Control.Applicative ((<|>))
import Data.Text (Text)
import GroundedPlanning.Compile.Sql.Aggregate (compileAggregateSql)
import GroundedPlanning.Compile.Sql.Common (labelsForRowObject, trendSeasonLabelFromFilters, trendSeasonTypeFromFilters)
import GroundedPlanning.Compile.Sql.Comparison (compileComparisonSql)
import GroundedPlanning.Compile.Sql.Find (compileFindSql)
import GroundedPlanning.Compile.Sql.Object (compileObjectSql)
import GroundedPlanning.Compile.Sql.Ranking (compileRankingSql)
import GroundedPlanning.Compile.Sql.Trend (compileTrendSql)
import GroundedPlanning.Plan
import GroundedPlanning.Resolve
import qualified QueryModel.IR as QI
import QueryModel.IR (Filter, filterIntValue, filterKindText, filterTextValue, filterValueRef)

-- Main compiler entry point.
-- Plain English: take the grounded semantic meaning from Resolve.hs and turn it
-- into the execution plan that Python runtime will later execute.
compileExecutionPlan :: ResolvedQuery -> ExecutionPlan
compileExecutionPlan resolvedQuery =
  case resolvedQuery of
    ResolvedMetric resolved -> compileMetricExecutionPlan resolved
    ResolvedTrend resolved -> compileTrendExecutionPlan resolved
    ResolvedObject resolved -> compileObjectExecutionPlan resolved
    ResolvedFind resolved -> compileFindExecutionPlan resolved

-- Build the top-level execution plan for metric questions.
-- This covers both ordinary ranking questions and comparison questions.
compileMetricExecutionPlan :: ResolvedMetricQuery -> ExecutionPlan
compileMetricExecutionPlan resolved@ResolvedMetricQuery {windowGames = metricWindowGames, timeFilterKind = metricTimeFilterKindValue, timeFilters = metricTimeFilters, queryLimit = metricQueryLimit, resolvedAssumptions = metricAssumptions, rowObjectName = metricRowObjectName, seasonLabel = metricSeasonLabel, seasonType = metricSeasonType, metricResultShape = resolvedResultShape, rowPredicateResolved = metricRowPredicate, resultPredicateResolved = metricResultPredicate, groupingDimensions = metricGroupingDimensions, displayMetadata = metricDisplayMetadata, displayMetricFormulas = metricDisplayMetricFormulas, metricTimeGrain = maybeMetricTimeGrain} =
  let formula =
        case resolved of
          ResolvedMetricQuery {metricFormula = currentFormula} -> currentFormula
      (singularLabel, pluralLabel, contextValueLabel) = labelsForRowObject metricRowObjectName
   in
  ExecutionPlan
    { plan_type =
        if comparisonRequestedValue resolved
          then "multi_step"
          else "single_sql"
    , query_kind = "metric_query"
    , result_shape =
        if comparisonRequestedValue resolved
          then "comparison"
          else resolvedResultShape
    , entity_label_singular = singularLabel
    , entity_label_plural = pluralLabel
    , context_label = contextValueLabel
    , metric = metricKey formula
    , metric_aggregation = aggregationKind formula
    , window_games = metricWindowGames
    , time_grain = maybeMetricTimeGrain
    , time_filter = Just metricTimeFilterKindValue
    , time_window_days = timeWindowDaysFromFilters metricTimeFilters
    , time_start_date = timeStartDateFromFilters metricTimeFilters
    , time_end_date = timeEndDateFromFilters metricTimeFilters
    , season_label = metricSeasonLabel
    , season_type = metricSeasonType
    , limit = maybe 0 id metricQueryLimit
    , assumptions = metricAssumptions
    , find_predicate_tree = Nothing
    , find_filters = []
    , row_predicate = planRowPredicateTree <$> metricRowPredicate
    , result_predicate = planResultPredicateTree <$> metricResultPredicate
    , grouping_columns = map planGroupingColumn metricGroupingDimensions
    , display_metadata = map planDisplayMetadata metricDisplayMetadata <> map planResultPredicateDisplayMetadata (resultPredicateAuxiliaryLeaves metricResultPredicate)
    , display_metrics = planDisplayMetrics metricDisplayMetricFormulas
    , steps = compileMetricSteps resolved
    }

-- Build the top-level execution plan for trend/time-series questions.
-- Trend plans are a single SQL step in the current runtime shape.
compileTrendExecutionPlan :: ResolvedTrendQuery -> ExecutionPlan
compileTrendExecutionPlan resolved@ResolvedTrendQuery {resolvedAssumptions = trendAssumptions, seriesObjectName = maybeSeriesObjectName, metricFormula = formula, timeGrain = trendTimeGrain, timeFilterKind = trendTimeFilter, trendFilters = trendFilterValues, trendSeasonLabel = maybeTrendSeasonLabel, trendSeasonType = maybeTrendSeasonType, trendRowPredicateResolved = trendRowPredicate, trendResultPredicateResolved = trendResultPredicate, trendGroupingDimensions = groupingDimensions} =
  let (singularLabel, pluralLabel, contextValueLabel) =
        case maybeSeriesObjectName of
          Just seriesObjectName ->
            labelsForRowObject seriesObjectName
          Nothing -> ("Series", "Series", "")
   in
  ExecutionPlan
    { plan_type = "single_sql"
    , query_kind = "metric_query"
    , result_shape = "time_series"
    , entity_label_singular = singularLabel
    , entity_label_plural = pluralLabel
    , context_label = contextValueLabel
    , metric = metricKey formula
    , metric_aggregation = aggregationKind formula
    , window_games = 0
    , time_grain = Just trendTimeGrain
    , time_filter = Just trendTimeFilter
    , time_window_days = timeWindowDaysFromFilters trendFilterValues
    , time_start_date = timeStartDateFromFilters trendFilterValues
    , time_end_date = timeEndDateFromFilters trendFilterValues
    , season_label = maybeTrendSeasonLabel <|> trendSeasonLabelFromFilters trendFilterValues
    , season_type = maybeTrendSeasonType <|> trendSeasonTypeFromFilters trendFilterValues
    , limit = 0
    , assumptions = trendAssumptions
    , find_predicate_tree = Nothing
    , find_filters = []
    , row_predicate = planRowPredicateTree <$> trendRowPredicate
    , result_predicate = planResultPredicateTree <$> trendResultPredicate
    , grouping_columns = map planGroupingColumn groupingDimensions
    , display_metadata = []
    , display_metrics = []
    , steps =
        [ PlanStep
            { kind = "run_sql"
            , sql = Just (compileTrendSql resolved)
            , analysis_spec = Nothing
            }
        ]
    }

-- Build the top-level execution plan for object-row questions.
-- Example shape: one row per player or one row per team.
compileObjectExecutionPlan :: ResolvedObjectQuery -> ExecutionPlan
compileObjectExecutionPlan resolved@ResolvedObjectQuery {windowGames = objectWindowGames, timeFilterKind = objectTimeFilterKind, timeFilters = objectTimeFilters, queryLimit = objectQueryLimit, resolvedAssumptions = objectAssumptions, rowObjectName = objectRowObjectName, seasonLabel = objectSeasonLabel, seasonType = objectSeasonType, objectRowPredicateResolved = objectRowPredicate, objectResultPredicateResolved = objectResultPredicate, displayMetadata = objectDisplayMetadata, displayMetricFormulas = objectDisplayMetricFormulas} =
  let formula =
        case resolved of
          ResolvedObjectQuery {metricFormula = currentFormula} -> currentFormula
      (singularLabel, pluralLabel, contextValueLabel) = labelsForRowObject objectRowObjectName
   in
  ExecutionPlan
    { plan_type = "single_sql"
    , query_kind = "object_query"
    , result_shape = "object_rows"
    , entity_label_singular = singularLabel
    , entity_label_plural = pluralLabel
    , context_label = contextValueLabel
    , metric = metricKey formula
    , metric_aggregation = aggregationKind formula
    , window_games = objectWindowGames
    , time_grain = Nothing
    , time_filter = Just objectTimeFilterKind
    , time_window_days = timeWindowDaysFromFilters objectTimeFilters
    , time_start_date = timeStartDateFromFilters objectTimeFilters
    , time_end_date = timeEndDateFromFilters objectTimeFilters
    , season_label = objectSeasonLabel
    , season_type = objectSeasonType
    , limit = maybe 0 id objectQueryLimit
    , assumptions = objectAssumptions
    , find_predicate_tree = Nothing
    , find_filters = []
    , row_predicate = planRowPredicateTree <$> objectRowPredicate
    , result_predicate = planResultPredicateTree <$> objectResultPredicate
    , grouping_columns = []
    , display_metadata = map planDisplayMetadata objectDisplayMetadata <> map planResultPredicateDisplayMetadata (resultPredicateAuxiliaryLeaves objectResultPredicate)
    , display_metrics = planDisplayMetrics objectDisplayMetricFormulas
    , steps =
        [ PlanStep
            { kind = "run_sql"
            , sql = Just (compileObjectSql resolved)
            , analysis_spec = Nothing
            }
        ]
    }

compileFindExecutionPlan :: ResolvedFindQuery -> ExecutionPlan
compileFindExecutionPlan resolved@ResolvedFindQuery {resolvedFindTargetObjectName = targetObjectNameValue, resolvedFindLimit = maybeFindLimit, resolvedFindAssumptions = findAssumptions, resolvedFindPredicateTree = maybePredicateTree, resolvedFindFilters = filterValues} =
  let (singularLabel, pluralLabel, contextValueLabel) = labelsForRowObject targetObjectNameValue
   in ExecutionPlan
        { plan_type = "single_sql"
        , query_kind = "find_query"
        , result_shape = "find_rows"
        , entity_label_singular = singularLabel
        , entity_label_plural = pluralLabel
        , context_label = contextValueLabel
        , metric = ""
        , metric_aggregation = ""
        , window_games = 0
        , time_grain = Nothing
        , time_filter = Just (metricTimeFilterKind filterValues)
        , time_window_days = timeWindowDaysFromFilters filterValues
        , time_start_date = timeStartDateFromFilters filterValues
        , time_end_date = timeEndDateFromFilters filterValues
        , season_label = Nothing
        , season_type = Nothing
        , limit = maybe 0 id maybeFindLimit
        , assumptions = findAssumptions
        , find_predicate_tree = planFindPredicateTree <$> maybePredicateTree
        , find_filters = map planFindFilter filterValues
        , row_predicate = Nothing
        , result_predicate = Nothing
        , grouping_columns = []
        , display_metadata = []
        , display_metrics = []
        , steps =
            [ PlanStep
                { kind = "run_sql"
                , sql = Just (compileFindSql resolved)
                , analysis_spec = Nothing
                }
            ]
        }

planFindPredicateTree :: ResolvedFindPredicateTree -> QI.Predicate
planFindPredicateTree predicateTree =
  case predicateTree of
    ResolvedFindPredicateLeafNode predicateLeaf ->
      QI.PredicateLeaf
        QI.PredicateField
          { QI.predicateFieldTargetObject = treePredicateTargetObjectName predicateLeaf
          , QI.predicateFieldAttribute = treePredicateLabel predicateLeaf
          , QI.predicateLocation = QI.PredicateRowField
          }
        (treePredicateOperator predicateLeaf)
        (treePredicateValue predicateLeaf)
    ResolvedFindPredicateAnd predicateValues ->
      QI.PredicateAnd (map planFindPredicateTree predicateValues)
    ResolvedFindPredicateOr predicateValues ->
      QI.PredicateOr (map planFindPredicateTree predicateValues)
    ResolvedFindPredicateNot predicateValue ->
      QI.PredicateNot (planFindPredicateTree predicateValue)

planFindFilter :: Filter -> PlanFindFilter
planFindFilter filterValue =
  PlanFindFilter
    { filter_kind = filterKindText filterValue
    , filter_value = filterValueRef filterValue
    }

timeWindowDaysFromFilters :: [Filter] -> Maybe Int
timeWindowDaysFromFilters filterValues =
  case filterValues of
    [] -> Nothing
    filterValue : remaining ->
      if filterKindText filterValue == "last_n_days"
        then filterIntValue filterValue
        else timeWindowDaysFromFilters remaining

timeStartDateFromFilters :: [Filter] -> Maybe Text
timeStartDateFromFilters filterValues =
  case filterValues of
    [] -> Nothing
    filterValue : remaining ->
      if filterKindText filterValue == "date_from"
        then filterTextValue filterValue
        else timeStartDateFromFilters remaining

timeEndDateFromFilters :: [Filter] -> Maybe Text
timeEndDateFromFilters filterValues =
  case filterValues of
    [] -> Nothing
    filterValue : remaining ->
      if filterKindText filterValue == "date_to"
        then filterTextValue filterValue
        else timeEndDateFromFilters remaining

planResultPredicateDisplayMetadata :: ResolvedResultPredicateLeaf -> PlanDisplayMetadata
planResultPredicateDisplayMetadata predicateLeaf =
  PlanDisplayMetadata
    { column_key = resultPredicateKey predicateLeaf
    , label = resultPredicateLabel predicateLeaf
    , column_type = "filter_metadata"
    }

planDisplayMetrics :: [ResolvedMetricFormula] -> [PlanDisplayMetric]
planDisplayMetrics metricFormulas =
  if length metricFormulas <= 1
    then []
    else map planDisplayMetric metricFormulas

planDisplayMetric :: ResolvedMetricFormula -> PlanDisplayMetric
planDisplayMetric formula =
  PlanDisplayMetric
    { column_key = resultColumn formula
    , metric = metricKey formula
    , label = metricKey formula
    }

planDisplayMetadata :: ResolvedDisplayMetadata -> PlanDisplayMetadata
planDisplayMetadata metadataValue =
  PlanDisplayMetadata
    { column_key = metadataKey metadataValue
    , label = metadataLabel metadataValue
    , column_type = metadataColumnType metadataValue
    }

planGroupingColumn :: ResolvedGroupingDimension -> PlanGroupingColumn
planGroupingColumn groupingDimension =
  PlanGroupingColumn
    { column_key = groupingKey groupingDimension
    , label = groupingLabel groupingDimension
    }

-- Decide which runtime steps a metric query needs.
-- Ordinary ranking questions are one SQL step.
-- Comparison questions are multi-step: first fetch rows with SQL, then ask the
-- Python runtime to do a comparison analysis step on those rows.
compileMetricSteps :: ResolvedMetricQuery -> [PlanStep]
compileMetricSteps resolved =
  if comparisonRequestedValue resolved
    then
      [ PlanStep
          { kind = "run_sql"
          , sql = Just (compileComparisonSql resolved)
          , analysis_spec = Nothing
          }
      , PlanStep
          { kind = "run_python"
          , sql = Nothing
          , analysis_spec = Just "CompareEntities"
          }
      ]
    else
      if metricResultShape resolved == "aggregate"
        then
          [ PlanStep
              { kind = "run_sql"
              , sql = Just (compileAggregateSql resolved)
              , analysis_spec = Nothing
              }
          ]
        else
          [ PlanStep
              { kind = "run_sql"
              , sql = Just (compileRankingSql resolved)
              , analysis_spec = Nothing
              }
          ]
