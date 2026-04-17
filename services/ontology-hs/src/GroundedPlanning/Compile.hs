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
    ResolvedObject resolved -> compileObjectExecutionPlan resolved

compileMetricExecutionPlan :: ResolvedMetricQuery -> ExecutionPlan
compileMetricExecutionPlan resolved@ResolvedMetricQuery {windowGames = metricWindowGames, queryLimit = metricQueryLimit, resolvedAssumptions = metricAssumptions, rowObjectName = metricRowObjectName} =
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
    , window_games = metricWindowGames
    , limit = maybe 0 id metricQueryLimit
    , assumptions = metricAssumptions
    , steps = compileMetricSteps resolved
    }

compileObjectExecutionPlan :: ResolvedObjectQuery -> ExecutionPlan
compileObjectExecutionPlan resolved@ResolvedObjectQuery {windowGames = objectWindowGames, queryLimit = objectQueryLimit, resolvedAssumptions = objectAssumptions, rowObjectName = objectRowObjectName} =
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
    , window_games = objectWindowGames
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
          , analysis_spec = Just "ComparePlayers"
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
compileRankingSql resolved =
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
          (map (\entityValue -> "'" <> entityColumnValue entityValue <> "'") resolvedComparisonEntities)
   in T.unlines $
        [ "WITH recent_rows AS ("
        , "  SELECT"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " AS player_name,"
        , "    " <> renderMaybeColumnRef "f" "r" "c" metricContextValue <> " AS team,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " AS game_date,"
        , "    " <> renderColumnRefWithContext "f" "r" "c" metricMetricSource <> " AS points,"
        , "    ROW_NUMBER() OVER ("
        , "      PARTITION BY " <> renderColumnRefWithContext "f" "r" "c" metricPartitionKey
        , "      ORDER BY " <> renderColumnRefWithContext "f" "r" "c" metricGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTableName <> " f"
        ]
          <> renderPathJoinClauses "JOIN" "f" "r" "rp" metricRowPath
          <> renderMaybePathJoinClauses "LEFT JOIN" "f" "c" "cp" metricContextPath
          <> [ "  WHERE " <> renderColumnRefWithContext "f" "r" "c" metricDisplayName <> " IN (" <> entityList <> ")"
        , ")"
        , "SELECT"
        , "  player_name,"
        , "  team,"
        , "  game_date,"
        , "  points"
        , "FROM recent_rows"
        , "WHERE game_rank <= " <> T.pack (show metricWindowGames)
        , "ORDER BY player_name ASC, game_date DESC"
        ]

compileObjectSql :: ResolvedObjectQuery -> Text
compileObjectSql resolved =
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

compileMetricAggregation :: ResolvedMetricFormula -> Text
compileMetricAggregation formula =
  case aggregationKind formula of
    "sum" -> "SUM(metric_source)"
    "avg" -> "ROUND(AVG(metric_source), 1)"
    _ -> error "Unsupported executable metric aggregation."

renderColumnRefWithContext :: Text -> Text -> Text -> ColumnRef -> Text
renderColumnRefWithContext factAlias rowAlias contextAlias columnRef =
  case tableRole columnRef of
    "fact" -> factAlias <> "." <> columnName columnRef
    "row" -> rowAlias <> "." <> columnName columnRef
    "context" -> contextAlias <> "." <> columnName columnRef
    _ -> error "Unsupported column role."

renderMaybeColumnRef :: Text -> Text -> Text -> Maybe ColumnRef -> Text
renderMaybeColumnRef factAlias rowAlias contextAlias maybeColumnRef =
  case maybeColumnRef of
    Just columnRef -> renderColumnRefWithContext factAlias rowAlias contextAlias columnRef
    Nothing -> "NULL"

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

limitClause :: Maybe Int -> [Text]
limitClause maybeLimit =
  case maybeLimit of
    Just limitValue -> ["LIMIT " <> T.pack (show limitValue)]
    Nothing -> []

labelsForRowObject :: Text -> (Text, Text, Text)
labelsForRowObject rowObjectNameValue =
  case rowObjectNameValue of
    "Player" -> ("Player", "Players", "Team")
    "Team" -> ("Team", "Teams", "Abbrev")
    _ -> ("Entity", "Entities", "Context")
