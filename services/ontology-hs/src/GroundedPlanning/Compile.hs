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

compileExecutionPlan :: ResolvedQuery -> ExecutionPlan
compileExecutionPlan resolvedQuery =
  case resolvedQuery of
    ResolvedMetric resolved -> compileMetricExecutionPlan resolved
    ResolvedObject resolved -> compileObjectExecutionPlan resolved

compileMetricExecutionPlan :: ResolvedMetricQuery -> ExecutionPlan
compileMetricExecutionPlan resolved@ResolvedMetricQuery {windowGames = metricWindowGames, queryLimit = metricQueryLimit, resolvedAssumptions = metricAssumptions} =
  let formula =
        case resolved of
          ResolvedMetricQuery {metricFormula = currentFormula} -> currentFormula
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
    , metric = metricKey formula
    , window_games = metricWindowGames
    , limit = maybe 0 id metricQueryLimit
    , assumptions = metricAssumptions
    , steps = compileMetricSteps resolved
    }

compileObjectExecutionPlan :: ResolvedObjectQuery -> ExecutionPlan
compileObjectExecutionPlan resolved@ResolvedObjectQuery {windowGames = objectWindowGames, queryLimit = objectQueryLimit, resolvedAssumptions = objectAssumptions} =
  let formula =
        case resolved of
          ResolvedObjectQuery {metricFormula = currentFormula} -> currentFormula
   in
  ExecutionPlan
    { plan_type = "single_sql"
    , query_kind = "object_query"
    , result_shape = "object_rows"
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
compileRankingSql ResolvedMetricQuery {factIdColumn = metricFactId, rowIdColumn = metricRowId, playerNameColumn = displayPlayerName, teamColumn = displayTeam, gameDateColumn = factGameDate, pointsColumn = factPoints, factTableName = metricFactTable, rowTableName = metricRowTable, windowGames = metricWindowGames, queryLimit = metricQueryLimit, metricFormula = resolvedMetricFormula} =
  T.unlines $
    [ "WITH recent_games AS ("
    , "  SELECT"
    , "    pg." <> metricFactId <> " AS player_id,"
    , "    p." <> displayPlayerName <> " AS player_name,"
    , "    pg." <> displayTeam <> " AS team,"
    , "    pg." <> factGameDate <> " AS game_date,"
    , "    pg." <> factPoints <> " AS points,"
    , "    ROW_NUMBER() OVER ("
    , "      PARTITION BY pg." <> metricFactId
    , "      ORDER BY pg." <> factGameDate <> " DESC"
    , "    ) AS game_rank"
    , "  FROM " <> metricFactTable <> " pg"
    , "  JOIN " <> metricRowTable <> " p"
    , "    ON pg." <> metricFactId <> " = p." <> metricRowId
    , "), ranked_players AS ("
    , "  SELECT"
    , "    player_name,"
    , "    arg_max(team, game_date) AS team,"
    , "    " <> compileMetricAggregation resolvedMetricFormula <> " AS metric_value"
    , "  FROM recent_games"
    , "  WHERE game_rank <= " <> T.pack (show metricWindowGames)
    , "  GROUP BY player_name"
    , ")"
    , "SELECT"
    , "  ROW_NUMBER() OVER (ORDER BY metric_value DESC, player_name ASC) AS rank,"
    , "  player_name,"
    , "  team,"
    , "  metric_value"
    , "FROM ranked_players"
    , "ORDER BY metric_value DESC, player_name ASC"
    ]
      <> limitClause metricQueryLimit

compileComparisonSql :: ResolvedMetricQuery -> Text
compileComparisonSql ResolvedMetricQuery {factIdColumn = metricFactId, rowIdColumn = metricRowId, playerNameColumn = displayPlayerName, teamColumn = displayTeam, gameDateColumn = factGameDate, pointsColumn = factPoints, factTableName = metricFactTable, rowTableName = metricRowTable, windowGames = metricWindowGames, comparisonEntities = resolvedComparisonEntities} =
  let
      entityList =
        T.intercalate
          ", "
          (map (\entityValue -> "'" <> entityColumnValue entityValue <> "'") resolvedComparisonEntities)
   in T.unlines
        [ "WITH recent_games AS ("
        , "  SELECT"
        , "    p." <> displayPlayerName <> " AS player_name,"
        , "    pg." <> displayTeam <> " AS team,"
        , "    pg." <> factGameDate <> " AS game_date,"
        , "    pg." <> factPoints <> " AS points,"
        , "    ROW_NUMBER() OVER ("
        , "      PARTITION BY pg." <> metricFactId
        , "      ORDER BY pg." <> factGameDate <> " DESC"
        , "    ) AS game_rank"
        , "  FROM " <> metricFactTable <> " pg"
        , "  JOIN " <> metricRowTable <> " p"
        , "    ON pg." <> metricFactId <> " = p." <> metricRowId
        , "  WHERE p." <> displayPlayerName <> " IN (" <> entityList <> ")"
        , ")"
        , "SELECT"
        , "  player_name,"
        , "  team,"
        , "  game_date,"
        , "  points"
        , "FROM recent_games"
        , "WHERE game_rank <= " <> T.pack (show metricWindowGames)
        , "ORDER BY player_name ASC, game_date DESC"
        ]

compileObjectSql :: ResolvedObjectQuery -> Text
compileObjectSql ResolvedObjectQuery {factIdColumn = objectFactId, rowIdColumn = objectRowId, playerNameColumn = displayPlayerName, teamColumn = displayTeam, gameDateColumn = factGameDate, pointsColumn = factPoints, factTableName = objectFactTable, rowTableName = objectRowTable, windowGames = objectWindowGames, queryLimit = objectQueryLimit, metricFormula = resolvedMetricFormula} =
  T.unlines $
    [ "WITH recent_games AS ("
    , "  SELECT"
    , "    pg." <> objectFactId <> " AS player_id,"
    , "    pg." <> factPoints <> " AS points,"
    , "    pg." <> displayTeam <> " AS team,"
    , "    pg." <> factGameDate <> " AS game_date,"
    , "    ROW_NUMBER() OVER ("
    , "      PARTITION BY pg." <> objectFactId
    , "      ORDER BY pg." <> factGameDate <> " DESC"
    , "    ) AS game_rank"
    , "  FROM " <> objectFactTable <> " pg"
    , "), player_values AS ("
    , "  SELECT"
    , "    player_id,"
    , "    arg_max(team, game_date) AS team,"
    , "    " <> compileMetricAggregation resolvedMetricFormula <> " AS metric_value"
    , "  FROM recent_games"
    , "  WHERE game_rank <= " <> T.pack (show objectWindowGames)
    , "  GROUP BY player_id"
    , ")"
    , "SELECT"
    , "  p." <> objectRowId <> " AS entity_id,"
    , "  p." <> displayPlayerName <> " AS player_name,"
    , "  pv.team AS team,"
    , "  pv.metric_value"
    , "FROM " <> objectRowTable <> " p"
    , "JOIN player_values pv"
    , "  ON p." <> objectRowId <> " = pv.player_id"
    , "ORDER BY pv.metric_value DESC, p." <> displayPlayerName <> " ASC"
    ]
      <> limitClause objectQueryLimit

compileMetricAggregation :: ResolvedMetricFormula -> Text
compileMetricAggregation ResolvedMetricFormula {metricKey = formulaMetricKey} =
  case formulaMetricKey of
    "total_points" -> "SUM(points)"
    "average_points" -> "ROUND(AVG(points), 1)"
    _ -> error "Unsupported executable metric formula."

limitClause :: Maybe Int -> [Text]
limitClause maybeLimit =
  case maybeLimit of
    Just limitValue -> ["LIMIT " <> T.pack (show limitValue)]
    Nothing -> []
