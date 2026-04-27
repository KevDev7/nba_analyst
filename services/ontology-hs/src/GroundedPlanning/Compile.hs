-- Purpose:
-- Compile the grounded query description into a runtime execution plan.
--
-- Uses:
-- - grounded table, link, and metric details from Resolve.hs
--
-- Produces:
-- - runtime execution plans for the Python runtime
--
-- Next:
-- - Main.hs

{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Plan
import GroundedPlanning.Resolve
import OntologyLayer.Graph (DiscoveredPath)
import qualified OntologyLayer.Graph as OG
import QueryModel.IR (Filter, FilterValue (FilterInt, FilterText), filterIntValue, filterKindText, filterTextValue)

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
compileMetricExecutionPlan resolved@ResolvedMetricQuery {windowGames = metricWindowGames, queryLimit = metricQueryLimit, resolvedAssumptions = metricAssumptions, rowObjectName = metricRowObjectName, seasonLabel = metricSeasonLabel, seasonType = metricSeasonType, metricResultShape = resolvedResultShape} =
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
    , steps = compileMetricSteps resolved
    }

-- Build the top-level execution plan for trend/time-series questions.
-- Trend plans are a single SQL step in the current runtime shape.
compileTrendExecutionPlan :: ResolvedTrendQuery -> ExecutionPlan
compileTrendExecutionPlan resolved@ResolvedTrendQuery {resolvedAssumptions = trendAssumptions, seriesObjectName = maybeSeriesObjectName, metricFormula = formula, timeGrain = trendTimeGrain, timeFilterKind = trendTimeFilter, trendFilters = trendFilterValues} =
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
compileObjectExecutionPlan resolved@ResolvedObjectQuery {windowGames = objectWindowGames, queryLimit = objectQueryLimit, resolvedAssumptions = objectAssumptions, rowObjectName = objectRowObjectName, seasonLabel = objectSeasonLabel, seasonType = objectSeasonType} =
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
    , steps =
        [ PlanStep
            { kind = "run_sql"
            , sql = Just (compileObjectSql resolved)
            , analysis_spec = Nothing
            }
        ]
    }

compileFindExecutionPlan :: ResolvedFindQuery -> ExecutionPlan
compileFindExecutionPlan resolved@ResolvedFindQuery {resolvedFindTargetObjectName = targetObjectNameValue, resolvedFindLimit = maybeFindLimit, resolvedFindAssumptions = findAssumptions} =
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
        , steps =
            [ PlanStep
                { kind = "run_sql"
                , sql = Just (compileFindSql resolved)
                , analysis_spec = Nothing
                }
            ]
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

-- Build SQL for ranking/top-N style questions.
-- There are two variants:
-- 1. season-scoped queries that can read directly from season-level rows
-- 2. recent-games queries that must rank rows, trim to the last N games, then aggregate
compileRankingSql :: ResolvedMetricQuery -> Text
compileRankingSql resolved@ResolvedMetricQuery {seasonLabel = maybeSeasonLabel, seasonType = maybeSeasonType} =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue) ->
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
          , queryLimit = metricQueryLimit
          , linkedFiltersResolved = metricLinkedFilters
          , metricOrderDirection = metricOrderDirectionValue
          } = resolved
       in
      T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricEntityId <> " AS entity_id,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_source,"
        , "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" metricPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
          <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
          <> renderLinkedFilterWhereClause "f" metricLinkedFilters
          <> [ "), ranked_entities AS ("
        , "  SELECT"
        , "    entity_id,"
        , "    arg_max(entity_name, game_date) AS entity_name,"
        , "    arg_max(context_value, game_date) AS context_value,"
        , "    " <> compileMetricAggregation resolvedMetricFormulaValue <> " AS metric_value"
        , "  FROM recent_rows"
        , "  WHERE game_rank <= " <> T.pack (show metricWindowGames)
        , "  GROUP BY entity_id"
        , ")"
        , "SELECT"
        , "  ROW_NUMBER() OVER (ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC) AS rank,"
        , "  entity_name,"
        , "  context_value,"
        , "  metric_value"
        , "FROM ranked_entities"
        , "ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC"
        ]
          <> limitClause metricQueryLimit

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

-- Build SQL for grouped aggregate questions.
-- This uses the same ontology-resolved fact/row paths as ranking, but returns
-- a summary table without rank numbering.
compileAggregateSql :: ResolvedMetricQuery -> Text
compileAggregateSql resolved@ResolvedMetricQuery {seasonLabel = maybeSeasonLabel, seasonType = maybeSeasonType} =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue) ->
      compileSeasonAggregateSql resolved seasonLabelValue seasonTypeValue
    _ ->
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
          , queryLimit = metricQueryLimit
          , linkedFiltersResolved = metricLinkedFilters
          } = resolved
       in
      T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS metric_source,"
        , "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" metricPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
          <> renderLinkedFilterWhereClause "f" metricLinkedFilters
          <> [ "), aggregate_groups AS ("
        , "  SELECT"
        , "    entity_name,"
        , "    MAX(context_value) AS context_value,"
        , "    " <> compileMetricAggregation resolvedMetricFormulaValue <> " AS metric_value"
        , "  FROM recent_rows"
        , "  WHERE game_rank <= " <> T.pack (show metricWindowGames)
        , "  GROUP BY entity_name"
        , ")"
        , "SELECT"
        , "  entity_name,"
        , "  context_value,"
        , "  metric_value"
        , "FROM aggregate_groups"
        , "ORDER BY entity_name ASC"
        ]
          <> limitClause metricQueryLimit

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

compileFindSql :: ResolvedFindQuery -> Text
compileFindSql resolved =
  let
    ResolvedFindQuery
      { resolvedFindFactTableName = factTableNameValue
      , resolvedFindTargetPath = targetPathValue
      , resolvedFindDisplays = displayValues
      , resolvedFindPredicates = predicateValues
      , resolvedFindFilters = findFilterValues
      , resolvedFindLimit = maybeFindLimit
      } = resolved
    selectLines = renderFindSelectLines displayValues predicateValues
    predicateJoinLines = concatMap renderIndexedFindPredicateJoin (zip [1 :: Int ..] predicateValues)
    whereConditions =
      map renderIndexedFindPredicateCondition (zip [1 :: Int ..] predicateValues)
        <> renderFindFilterConditions factTableNameValue findFilterValues
    maybeLastNGames = findLastNGames findFilterValues
   in
  case maybeLastNGames of
    Just gamesValue ->
      T.unlines $
        [ "WITH filtered_find_rows AS ("
        , "  SELECT"
        ]
          <> indentFindSelectLines selectLines
          <> [ "    f.game_date AS __find_game_date,"
             , "    ROW_NUMBER() OVER (ORDER BY f.game_date DESC) AS __find_row_rank"
             , "  FROM " <> factTableNameValue <> " f"
             ]
          <> renderPathJoinClauses "JOIN" "f" "r" "fp" targetPathValue
          <> predicateJoinLines
          <> [ "  WHERE " <> combineWhereClauses whereConditions
             , ")"
             , "SELECT DISTINCT " <> T.intercalate ", " (findSelectedLabels displayValues predicateValues)
             , "FROM filtered_find_rows"
             , "WHERE __find_row_rank <= " <> T.pack (show gamesValue)
             , "ORDER BY " <> findOrderColumn displayValues
             ]
          <> limitClause maybeFindLimit
    Nothing ->
      T.unlines $
        [ "SELECT DISTINCT"
        ]
          <> selectLines
          <> [ "FROM " <> factTableNameValue <> " f" ]
          <> renderPathJoinClauses "JOIN" "f" "r" "fp" targetPathValue
          <> predicateJoinLines
          <> [ "WHERE " <> combineWhereClauses whereConditions
             , "ORDER BY " <> findOrderColumn displayValues
             ]
          <> limitClause maybeFindLimit

renderFindSelectLines :: [ResolvedFindDisplay] -> [ResolvedFindPredicate] -> [Text]
renderFindSelectLines displayValues predicateValues =
  map renderDisplay (markLast (displaySelections <> predicateSelections))
  where
    displaySelections =
      [ (displayLabel displayValue, findPathAlias "r" (displayPath displayValue), displayColumn displayValue)
      | displayValue <- displayValues
      ]
    predicateSelections =
      [ (predicateLabel predicateValue, findPredicateAlias indexValue predicateValue, predicateColumn predicateValue)
      | (indexValue, predicateValue) <- zip [1 :: Int ..] predicateValues
      , predicateLabel predicateValue `notElem` map displayLabel displayValues
      ]
    renderDisplay (isLastValue, (labelValue, aliasValue, columnValue)) =
      "  " <> aliasValue <> "." <> columnValue <> " AS " <> labelValue <> if isLastValue then "" else ","

indentFindSelectLines :: [Text] -> [Text]
indentFindSelectLines selectLines =
  map ensureComma selectLines
  where
    ensureComma lineValue =
      let indentedLine = "  " <> lineValue
       in if "," `T.isSuffixOf` indentedLine
            then indentedLine
            else indentedLine <> ","

findSelectedLabels :: [ResolvedFindDisplay] -> [ResolvedFindPredicate] -> [Text]
findSelectedLabels displayValues predicateValues =
  displayLabels <> predicateLabels
  where
    displayLabels = map displayLabel displayValues
    predicateLabels =
      [ predicateLabel predicateValue
      | predicateValue <- predicateValues
      , predicateLabel predicateValue `notElem` displayLabels
      ]

markLast :: [a] -> [(Bool, a)]
markLast values =
  case values of
    [] -> []
    [value] -> [(True, value)]
    value : remaining -> (False, value) : markLast remaining

renderIndexedFindPredicateJoin :: (Int, ResolvedFindPredicate) -> [Text]
renderIndexedFindPredicateJoin (indexValue, predicateValue) =
  if null (OG.steps (predicatePath predicateValue))
    then []
    else renderPathJoinClauses "JOIN" "f" (findPredicateAlias indexValue predicateValue) ("pr" <> T.pack (show indexValue) <> "p") (predicatePath predicateValue)

renderIndexedFindPredicateCondition :: (Int, ResolvedFindPredicate) -> Text
renderIndexedFindPredicateCondition (indexValue, predicateValueResolved) =
  findPredicateAlias indexValue predicateValueResolved
    <> "."
    <> predicateColumn predicateValueResolved
    <> " "
    <> predicateOp predicateValueResolved
    <> " "
    <> renderFilterLiteral (predicateValue predicateValueResolved)

findPredicateAlias :: Int -> ResolvedFindPredicate -> Text
findPredicateAlias indexValue predicateValue =
  findPathAlias ("pr" <> T.pack (show indexValue)) (predicatePath predicateValue)

findPathAlias :: Text -> DiscoveredPath -> Text
findPathAlias nonFactAlias pathValue =
  if null (OG.steps pathValue)
    then "f"
    else nonFactAlias

findOrderColumn :: [ResolvedFindDisplay] -> Text
findOrderColumn displayValues =
  case displayValues of
    displayValue : _ -> displayLabel displayValue <> " DESC"
    [] -> "1"

findLastNGames :: [Filter] -> Maybe Int
findLastNGames filterValues =
  case filterValues of
    [] -> Nothing
    filterValue : remaining ->
      if filterKindText filterValue == "last_n_games"
        then filterIntValue filterValue
        else findLastNGames remaining

renderFindFilterConditions :: Text -> [Filter] -> [Text]
renderFindFilterConditions findFactTableName filterValues =
  mapMaybeFindFilterCondition filterValues
  where
    latestDateSubquery = "(SELECT MAX(game_date) FROM " <> findFactTableName <> ")"
    mapMaybeFindFilterCondition [] = []
    mapMaybeFindFilterCondition (filterValue : remaining) =
      case filterKindText filterValue of
        "last_n_games" -> mapMaybeFindFilterCondition remaining
        "past_year" ->
          ("f.game_date >= " <> latestDateSubquery <> " - INTERVAL '1 year'") : mapMaybeFindFilterCondition remaining
        "exact_season" ->
          case filterTextValue filterValue of
            Just seasonLabelValue -> ("f.season_year = '" <> escapeSqlLiteral seasonLabelValue <> "'") : mapMaybeFindFilterCondition remaining
            Nothing -> mapMaybeFindFilterCondition remaining
        "season_type" ->
          case filterTextValue filterValue of
            Just seasonTypeValue -> ("f.season_type = '" <> escapeSqlLiteral seasonTypeValue <> "'") : mapMaybeFindFilterCondition remaining
            Nothing -> mapMaybeFindFilterCondition remaining
        _ -> mapMaybeFindFilterCondition remaining

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
      , linkedFiltersResolved = metricLinkedFilters
      , metricOrderDirection = metricOrderDirectionValue
      } = resolved
   in
  T.unlines $
    [ "WITH season_ranked_entities AS ("
    , "  SELECT"
    , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
    , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
    , "    " <> renderMetricValue metricMetricSource <> " AS metric_value"
    , "  FROM " <> metricFactTableName <> " f"
    ]
      <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
      <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
      <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
      <> [ "  WHERE " <> combineWhereClauses (seasonWhereClause seasonLabelValue seasonTypeValue : renderLinkedFilterConditions "f" metricLinkedFilters)
         , "    AND " <> renderMetricValue metricMetricSource <> " IS NOT NULL"
         , ")"
         , "SELECT"
    , "  ROW_NUMBER() OVER (ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC) AS rank,"
         , "  entity_name,"
         , "  context_value,"
         , "  metric_value"
         , "FROM season_ranked_entities"
         , "ORDER BY metric_value " <> metricOrderDirectionValue <> ", entity_name ASC"
         ]
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
      , linkedFiltersResolved = metricLinkedFilters
      } = resolved
   in
  T.unlines $
    [ "WITH season_rows AS ("
    , "  SELECT"
    , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS entity_name,"
    , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS context_value,"
    , "    " <> renderMetricValue metricMetricSource <> " AS metric_source"
    , "  FROM " <> metricFactTableName <> " f"
    ]
      <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
      <> renderLinkedFilterJoinClauses "f" metricLinkedFilters
      <> [ "  WHERE " <> combineWhereClauses (seasonWhereClause seasonLabelValue seasonTypeValue : renderLinkedFilterConditions "f" metricLinkedFilters)
         , "    AND " <> renderMetricValue metricMetricSource <> " IS NOT NULL"
         , "), aggregate_groups AS ("
         , "  SELECT"
         , "    entity_name,"
         , "    MAX(context_value) AS context_value,"
         , "    " <> compileMetricAggregation metricFormulaValue <> " AS metric_value"
         , "  FROM season_rows"
         , "  GROUP BY entity_name"
         , ")"
         , "SELECT"
         , "  entity_name,"
         , "  context_value,"
         , "  metric_value"
         , "FROM aggregate_groups"
         , "ORDER BY entity_name ASC"
         ]
      <> limitClause metricQueryLimit

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

-- Turn the resolved metric aggregation into the SQL aggregation expression.
-- This is where a semantic aggregation like "sum" becomes concrete SQL like SUM(...).
compileMetricAggregation :: ResolvedMetricFormula -> Text
compileMetricAggregation formula =
  case aggregationKind formula of
    "sum" -> "SUM(metric_source)"
    "avg" -> "ROUND(AVG(metric_source), 1)"
    "identity" -> "MAX(metric_source)"
    _ -> error "Unsupported executable metric aggregation."

renderTrendFilterConditions :: Text -> [Filter] -> [Text]
renderTrendFilterConditions trendFactTableName filterValues =
  mapMaybeTrendFilterCondition filterValues
  where
    latestDateSubquery = "(SELECT MAX(game_date) FROM " <> trendFactTableName <> ")"
    mapMaybeTrendFilterCondition [] = []
    mapMaybeTrendFilterCondition (filterValue : remaining) =
      case filterKindText filterValue of
        "past_year" ->
          ("f.game_date >= " <> latestDateSubquery <> " - INTERVAL '1 year'") : mapMaybeTrendFilterCondition remaining
        "season_type" ->
          case filterTextValue filterValue of
            Just seasonTypeValue -> ("f.season_type = '" <> seasonTypeValue <> "'") : mapMaybeTrendFilterCondition remaining
            Nothing -> mapMaybeTrendFilterCondition remaining
        _ -> mapMaybeTrendFilterCondition remaining

trendSeasonTypeFromFilters :: [Filter] -> Maybe Text
trendSeasonTypeFromFilters filterValues =
  case filterValues of
    [] -> Nothing
    filterValue : remaining ->
      if filterKindText filterValue == "season_type"
        then filterTextValue filterValue
        else trendSeasonTypeFromFilters remaining

-- Render a metric column reference based on where it lives in the query shape.
renderMetricValue :: ColumnRef -> Text
renderMetricValue columnRef =
  case tableRole columnRef of
    "fact" -> "f." <> columnName columnRef
    "row" -> "r." <> columnName columnRef
    "series" -> "r." <> columnName columnRef
    "context" -> "c." <> columnName columnRef
    _ -> error "Unsupported metric column role."

seasonWhereClause :: Text -> Text -> Text
seasonWhereClause seasonLabelValue seasonTypeValue =
  "f.season_year = '" <> seasonLabelValue <> "' AND f.season_type = '" <> seasonTypeValue <> "'"

combineWhereClauses :: [Text] -> Text
combineWhereClauses clauseValues =
  T.intercalate " AND " clauseValues

-- Render a column reference using the right table alias for its role.
-- Example: a fact column becomes f.column_name, a row column becomes r.column_name.
renderColumnRefWithContext :: Text -> Text -> Text -> ColumnRef -> Text
renderColumnRefWithContext factAlias rowAlias contextAlias columnRef =
  case tableRole columnRef of
    "fact" -> factAlias <> "." <> columnName columnRef
    "row" -> rowAlias <> "." <> columnName columnRef
    "series" -> rowAlias <> "." <> columnName columnRef
    "context" -> contextAlias <> "." <> columnName columnRef
    _ -> error "Unsupported column role."

renderMaybeColumnRef :: Text -> Text -> Text -> Maybe ColumnRef -> Text
renderMaybeColumnRef factAlias rowAlias contextAlias maybeColumnRef =
  case maybeColumnRef of
    Just columnRef -> renderColumnRefWithContext factAlias rowAlias contextAlias columnRef
    Nothing -> "NULL"

renderFactExpression :: Text -> Text -> Text
renderFactExpression factAlias expressionText =
  T.replace "{fact_alias}" factAlias expressionText

-- Turn a discovered ontology path into SQL JOIN clauses.
-- Plain English: if Resolve.hs said "to get from the fact object to the row object,
-- walk these links", this helper turns that path into actual JOIN lines.
renderPathJoinClauses :: Text -> Text -> Text -> Text -> DiscoveredPath -> [Text]
renderPathJoinClauses joinKeyword baseAlias finalAlias intermediatePrefix discoveredPath =
  case OG.steps discoveredPath of
    [] -> []
    discoveredSteps ->
      concatMap renderIndexedStep (zip [0 :: Int ..] discoveredSteps)
      where
        finalIndex = length discoveredSteps - 1

        aliasAt :: Int -> Text
        aliasAt indexValue =
          if indexValue == finalIndex
            then finalAlias
            else intermediatePrefix <> T.pack (show (indexValue + 1))

        sourceAliasAt :: Int -> Text
        sourceAliasAt indexValue =
          if indexValue == 0
            then baseAlias
            else aliasAt (indexValue - 1)

        renderIndexedStep :: (Int, OG.PathStep) -> [Text]
        renderIndexedStep (indexValue, discoveredStep) =
          let targetAlias = aliasAt indexValue
              sourceAlias = sourceAliasAt indexValue
           in
          [ "  " <> joinKeyword <> " " <> OG.stepTargetTableName discoveredStep <> " " <> targetAlias
          , "    ON " <> sourceAlias <> "." <> OG.sourceKey discoveredStep <> " = " <> targetAlias <> "." <> OG.targetKey discoveredStep
          ]

renderMaybePathJoinClauses :: Text -> Text -> Text -> Text -> Maybe DiscoveredPath -> [Text]
renderMaybePathJoinClauses joinKeyword baseAlias finalAlias intermediatePrefix maybeDiscoveredPath =
  case maybeDiscoveredPath of
    Just discoveredPath -> renderPathJoinClauses joinKeyword baseAlias finalAlias intermediatePrefix discoveredPath
    Nothing -> []

-- Add JOIN clauses needed for linked filters like "players on the Knicks".
renderLinkedFilterJoinClauses :: Text -> [ResolvedLinkedFilter] -> [Text]
renderLinkedFilterJoinClauses baseAlias linkedFilterValues =
  concatMap renderIndexedFilter (zip [1 :: Int ..] linkedFilterValues)
  where
    renderIndexedFilter :: (Int, ResolvedLinkedFilter) -> [Text]
    renderIndexedFilter (indexValue, linkedFilterValue) =
      renderPathJoinClauses
        "JOIN"
        baseAlias
        (linkedFilterAlias indexValue linkedFilterValue)
        ("lf" <> T.pack (show indexValue) <> "p")
        (filterPath linkedFilterValue)

-- Add the WHERE wrapper for linked-filter conditions when any exist.
renderLinkedFilterWhereClause :: Text -> [ResolvedLinkedFilter] -> [Text]
renderLinkedFilterWhereClause baseAlias linkedFilterValues =
  case renderLinkedFilterConditions baseAlias linkedFilterValues of
    [] -> []
    conditions -> ["  WHERE " <> combineWhereClauses conditions]

-- Render the individual linked-filter predicates.
renderLinkedFilterConditions :: Text -> [ResolvedLinkedFilter] -> [Text]
renderLinkedFilterConditions baseAlias linkedFilterValues =
  map renderIndexedCondition (zip [1 :: Int ..] linkedFilterValues)
  where
    renderIndexedCondition :: (Int, ResolvedLinkedFilter) -> Text
    renderIndexedCondition (indexValue, linkedFilterValue) =
      linkedFilterAlias indexValue linkedFilterValue
        <> "."
        <> filterColumn linkedFilterValue
        <> " = '"
        <> escapeSqlLiteral (filterValue linkedFilterValue)
        <> "'"

linkedFilterAlias :: Int -> ResolvedLinkedFilter -> Text
linkedFilterAlias indexValue linkedFilterValue =
  if null (OG.steps (filterPath linkedFilterValue))
    then "f"
    else "lf" <> T.pack (show indexValue)

escapeSqlLiteral :: Text -> Text
escapeSqlLiteral = T.replace "'" "''"

renderFilterLiteral :: FilterValue -> Text
renderFilterLiteral filterValue =
  case filterValue of
    FilterInt intValue -> T.pack (show intValue)
    FilterText textValue -> "'" <> escapeSqlLiteral textValue <> "'"

-- Turn an optional limit into a SQL LIMIT clause.
limitClause :: Maybe Int -> [Text]
limitClause maybeLimit =
  case maybeLimit of
    Just limitValue -> ["LIMIT " <> T.pack (show limitValue)]
    Nothing -> []

-- User-facing labels that Python/UI can show for result rows.
-- This is presentation metadata that rides along with the execution plan.
labelsForRowObject :: Text -> (Text, Text, Text)
labelsForRowObject rowObjectNameValue =
  case rowObjectNameValue of
    "Game" -> ("Game", "Games", "")
    "Player" -> ("Player", "Players", "Team")
    "PlayerSeason" -> ("Player", "Players", "")
    "Team" -> ("Team", "Teams", "Abbrev")
    "TeamSeason" -> ("Team", "Teams", "Abbrev")
    _ -> ("Entity", "Entities", "Context")
