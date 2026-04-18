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

compileExecutionPlan :: ResolvedQuery -> ExecutionPlan
compileExecutionPlan resolvedQuery =
  case resolvedQuery of
    ResolvedMetric resolved -> compileMetricExecutionPlan resolved
    ResolvedTrend resolved -> compileTrendExecutionPlan resolved
    ResolvedObject resolved -> compileObjectExecutionPlan resolved

compileMetricExecutionPlan :: ResolvedMetricQuery -> ExecutionPlan
compileMetricExecutionPlan resolved@ResolvedMetricQuery {windowGames = metricWindowGames, queryLimit = metricQueryLimit, resolvedAssumptions = metricAssumptions, rowObjectName = metricRowObjectName, seasonLabel = metricSeasonLabel, seasonType = metricSeasonType} =
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
          else "ranking"
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

compileTrendExecutionPlan :: ResolvedTrendQuery -> ExecutionPlan
compileTrendExecutionPlan resolved@ResolvedTrendQuery {resolvedAssumptions = trendAssumptions, seriesObjectName = maybeSeriesObjectName, metricFormula = formula, timeGrain = trendTimeGrain, timeFilterKind = trendTimeFilter} =
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
    , season_type = Nothing
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
      [ PlanStep
          { kind = "run_sql"
          , sql = Just (compileRankingSql resolved)
          , analysis_spec = Nothing
          }
      ]

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
        , "  ROW_NUMBER() OVER (ORDER BY metric_value DESC, entity_name ASC) AS rank,"
        , "  entity_name,"
        , "  context_value,"
        , "  metric_value"
        , "FROM ranked_entities"
        , "ORDER BY metric_value DESC, entity_name ASC"
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
          <> [ "  WHERE " <> renderColumnRefWithContext "f" "r" "c" metricEntityId <> " IN (" <> entityList <> ")"
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
        , "ORDER BY metric_value DESC, entity_name ASC"
        ]
          <> limitClause objectQueryLimit

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
      } = resolved
    latestDateSubquery = "(SELECT MAX(game_date) FROM " <> trendFactTableName <> ")"
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
      <> [ "  WHERE f.game_date >= " <> latestDateSubquery <> " - INTERVAL '1 year'"
         , "), aggregated_series AS ("
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
         , "  ROW_NUMBER() OVER (ORDER BY metric_value DESC, entity_name ASC) AS rank,"
         , "  entity_name,"
         , "  context_value,"
         , "  metric_value"
         , "FROM season_ranked_entities"
         , "ORDER BY metric_value DESC, entity_name ASC"
         ]
      <> limitClause metricQueryLimit

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
         , "ORDER BY metric_value DESC, entity_name ASC"
         ]
      <> limitClause objectQueryLimit

compileMetricAggregation :: ResolvedMetricFormula -> Text
compileMetricAggregation formula =
  case aggregationKind formula of
    "sum" -> "SUM(metric_source)"
    "avg" -> "ROUND(AVG(metric_source), 1)"
    _ -> error "Unsupported executable metric aggregation."

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

renderLinkedFilterWhereClause :: Text -> [ResolvedLinkedFilter] -> [Text]
renderLinkedFilterWhereClause baseAlias linkedFilterValues =
  case renderLinkedFilterConditions baseAlias linkedFilterValues of
    [] -> []
    conditions -> ["  WHERE " <> combineWhereClauses conditions]

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

limitClause :: Maybe Int -> [Text]
limitClause maybeLimit =
  case maybeLimit of
    Just limitValue -> ["LIMIT " <> T.pack (show limitValue)]
    Nothing -> []

labelsForRowObject :: Text -> (Text, Text, Text)
labelsForRowObject rowObjectNameValue =
  case rowObjectNameValue of
    "Player" -> ("Player", "Players", "Team")
    "PlayerSeason" -> ("Player", "Players", "")
    "Team" -> ("Team", "Teams", "Abbrev")
    "TeamSeason" -> ("Team", "Teams", "Abbrev")
    _ -> ("Entity", "Entities", "Context")
