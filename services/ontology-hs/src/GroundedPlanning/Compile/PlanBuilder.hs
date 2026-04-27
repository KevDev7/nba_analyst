-- Purpose:
-- Build runtime execution-plan envelopes from resolved semantic queries.
--
-- SQL text is delegated to GroundedPlanning.Compile.Sql.* modules.

{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.PlanBuilder (compileExecutionPlan) where

import GroundedPlanning.Compile.Sql.Aggregate (compileAggregateSql)
import GroundedPlanning.Compile.Sql.Common (labelsForRowObject, trendSeasonTypeFromFilters)
import GroundedPlanning.Compile.Sql.Comparison (compileComparisonSql)
import GroundedPlanning.Compile.Sql.Find (compileFindSql)
import GroundedPlanning.Compile.Sql.Object (compileObjectSql)
import GroundedPlanning.Compile.Sql.Ranking (compileRankingSql)
import GroundedPlanning.Compile.Sql.Trend (compileTrendSql)
import GroundedPlanning.Plan
import GroundedPlanning.Resolve
import QueryModel.IR (Filter, filterKindText, filterValueRef)

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
compileMetricExecutionPlan resolved@ResolvedMetricQuery {windowGames = metricWindowGames, queryLimit = metricQueryLimit, resolvedAssumptions = metricAssumptions, rowObjectName = metricRowObjectName, seasonLabel = metricSeasonLabel, seasonType = metricSeasonType, metricResultShape = resolvedResultShape, linkedFiltersResolved = metricLinkedFilters, displayMetadata = metricDisplayMetadata} =
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
    , time_grain = Nothing
    , time_filter = Nothing
    , season_label = metricSeasonLabel
    , season_type = metricSeasonType
    , limit = maybe 0 id metricQueryLimit
    , assumptions = metricAssumptions
    , find_predicates = []
    , find_filters = []
    , linked_filters = map planLinkedFilter metricLinkedFilters
    , display_metadata = map planDisplayMetadata metricDisplayMetadata
    , steps = compileMetricSteps resolved
    }

-- Build the top-level execution plan for trend/time-series questions.
-- Trend plans are a single SQL step in the current runtime shape.
compileTrendExecutionPlan :: ResolvedTrendQuery -> ExecutionPlan
compileTrendExecutionPlan resolved@ResolvedTrendQuery {resolvedAssumptions = trendAssumptions, seriesObjectName = maybeSeriesObjectName, metricFormula = formula, timeGrain = trendTimeGrain, timeFilterKind = trendTimeFilter, trendFilters = trendFilterValues, linkedFiltersResolved = trendLinkedFilters} =
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
    , season_label = Nothing
    , season_type = trendSeasonTypeFromFilters trendFilterValues
    , limit = 0
    , assumptions = trendAssumptions
    , find_predicates = []
    , find_filters = []
    , linked_filters = map planLinkedFilter trendLinkedFilters
    , display_metadata = []
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
compileObjectExecutionPlan resolved@ResolvedObjectQuery {windowGames = objectWindowGames, queryLimit = objectQueryLimit, resolvedAssumptions = objectAssumptions, rowObjectName = objectRowObjectName, seasonLabel = objectSeasonLabel, seasonType = objectSeasonType, linkedFiltersResolved = objectLinkedFilters, displayMetadata = objectDisplayMetadata} =
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
    , time_filter = Nothing
    , season_label = objectSeasonLabel
    , season_type = objectSeasonType
    , limit = maybe 0 id objectQueryLimit
    , assumptions = objectAssumptions
    , find_predicates = []
    , find_filters = []
    , linked_filters = map planLinkedFilter objectLinkedFilters
    , display_metadata = map planDisplayMetadata objectDisplayMetadata
    , steps =
        [ PlanStep
            { kind = "run_sql"
            , sql = Just (compileObjectSql resolved)
            , analysis_spec = Nothing
            }
        ]
    }

compileFindExecutionPlan :: ResolvedFindQuery -> ExecutionPlan
compileFindExecutionPlan resolved@ResolvedFindQuery {resolvedFindTargetObjectName = targetObjectNameValue, resolvedFindLimit = maybeFindLimit, resolvedFindAssumptions = findAssumptions, resolvedFindPredicates = predicateValues, resolvedFindFilters = filterValues} =
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
        , time_filter = Nothing
        , season_label = Nothing
        , season_type = Nothing
        , limit = maybe 0 id maybeFindLimit
        , assumptions = findAssumptions
        , find_predicates = map planFindPredicate predicateValues
        , find_filters = map planFindFilter filterValues
        , linked_filters = []
        , display_metadata = []
        , steps =
            [ PlanStep
                { kind = "run_sql"
                , sql = Just (compileFindSql resolved)
                , analysis_spec = Nothing
                }
            ]
        }

planFindPredicate :: ResolvedFindPredicate -> PlanFindPredicate
planFindPredicate predicateResolved =
  PlanFindPredicate
    { target_object = predicateTargetObjectName predicateResolved
    , attribute = predicateLabel predicateResolved
    , operator = predicateOp predicateResolved
    , value = predicateValue predicateResolved
    }

planFindFilter :: Filter -> PlanFindFilter
planFindFilter filterValue =
  PlanFindFilter
    { filter_kind = filterKindText filterValue
    , filter_value = filterValueRef filterValue
    }

planLinkedFilter :: ResolvedLinkedFilter -> PlanLinkedFilter
planLinkedFilter linkedFilterValue =
  PlanLinkedFilter
    { target_object = targetObjectName linkedFilterValue
    , attribute = filterColumn linkedFilterValue
    , value = filterValue linkedFilterValue
    }

planDisplayMetadata :: ResolvedDisplayMetadata -> PlanDisplayMetadata
planDisplayMetadata metadataValue =
  PlanDisplayMetadata
    { column_key = metadataKey metadataValue
    , label = metadataLabel metadataValue
    , column_type = metadataColumnType metadataValue
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
