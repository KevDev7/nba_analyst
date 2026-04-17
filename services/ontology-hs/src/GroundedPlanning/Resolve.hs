-- Purpose:
-- Resolve the validated Query into grounded table, link, and metric-formula details.
--
-- Uses:
-- - typed ontology values
-- - validated Query IR
--
-- Produces:
-- - a grounded query description ready for compilation
--
-- Next:
-- - Compile.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve where

import Data.Aeson (FromJSON, ToJSON (toJSON), object, (.=))
import Data.Text (Text)
import GHC.Generics (Generic)
import OntologyLayer.Graph (findLink, findMetric, findObject)
import OntologyLayer.Types (Link (source_key, target_key), MetricDef (aggregation, executable, expression, name, source_attributes), Object (backing_table), Ontology)
import QueryModel.IR

data ResolvedEntity = ResolvedEntity
  { entityName :: EntityName
  , entityColumnValue :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data JoinPath = JoinPath
  { factTable :: Text
  , factJoinKey :: Text
  , rowTable :: Text
  , rowJoinKey :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedMetricFormula = ResolvedMetricFormula
  { metricKey :: Text
  , aggregationKind :: Text
  , sourceAttributes :: [Text]
  , expressionText :: Text
  , executableInSlice :: Bool
  , resultColumn :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedMetricQuery = ResolvedMetricQuery
  { factTableName :: Text
  , rowTableName :: Text
  , factIdColumn :: Text
  , rowIdColumn :: Text
  , playerNameColumn :: Text
  , teamColumn :: Text
  , gameDateColumn :: Text
  , pointsColumn :: Text
  , minutesColumn :: Text
  , windowGames :: Int
  , queryLimit :: Maybe Int
  , comparisonEntities :: [ResolvedEntity]
  , comparisonRequestedValue :: Bool
  , resolvedAssumptions :: [Text]
  , joinPath :: JoinPath
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedObjectQuery = ResolvedObjectQuery
  { rowTableName :: Text
  , factTableName :: Text
  , rowObjectName :: Text
  , factIdColumn :: Text
  , rowIdColumn :: Text
  , playerNameColumn :: Text
  , teamColumn :: Text
  , gameDateColumn :: Text
  , pointsColumn :: Text
  , minutesColumn :: Text
  , windowGames :: Int
  , queryLimit :: Maybe Int
  , resolvedAssumptions :: [Text]
  , joinPath :: JoinPath
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedQuery
  = ResolvedMetric ResolvedMetricQuery
  | ResolvedObject ResolvedObjectQuery
  deriving (Show, Eq, Generic)

instance ToJSON ResolvedQuery where
  toJSON (ResolvedMetric resolved) =
    object ["kind" .= ("metric_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedObject resolved) =
    object ["kind" .= ("object_query" :: Text), "resolved" .= resolved]

resolveQuery :: Ontology -> Query -> Either Text ResolvedQuery
resolveQuery ontology query =
  case query of
    MetricQuery spec -> ResolvedMetric <$> resolveMetricQuery ontology spec
    ObjectQuery spec -> ResolvedObject <$> resolveObjectQuery ontology spec

resolveMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ResolvedMetricQuery
resolveMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec currentBase _ _ -> currentBase
  playerGameObject <- maybe (Left "Could not resolve PlayerGame against the ontology.") Right $
    findObject ontology (coreFactObject base)
  playerObject <- maybe (Left "Could not resolve Player against the ontology.") Right $
    findObject ontology "Player"
  link <- maybe (Left "Could not resolve the PlayerGame -> Player link.") Right $
    findLink ontology "PlayerGame" "Player"
  selectedMetric <-
    case metrics base of
      [metricValue] -> Right metricValue
      _ -> Left "MetricQuery requires exactly one selected metric."
  metricDef <- maybe (Left "Could not resolve the selected metric against the ontology.") Right $
    findMetric playerGameObject (metricText selectedMetric)
  gamesValue <-
    case filters base of
      [LastNGames n] -> Right n
      _ -> Left "Only a single LastNGames filter is supported."
  let limitValue = limit base
      entityValues = map resolveEntity (entityFilters metricQuery)
      comparisonRequestedFlag =
        case comparison metricQuery of
          Just _ -> True
          Nothing -> False
      joinPathValue =
        JoinPath
          { factTable = backing_table playerGameObject
          , factJoinKey = source_key link
          , rowTable = backing_table playerObject
          , rowJoinKey = target_key link
          }
      formula = resolveMetricFormula metricDef
  pure
    ResolvedMetricQuery
      { factTableName = backing_table playerGameObject
      , rowTableName = backing_table playerObject
      , factIdColumn = source_key link
      , rowIdColumn = target_key link
      , playerNameColumn = "player_name"
      , teamColumn = "team"
      , gameDateColumn = "game_date"
      , pointsColumn = "points"
      , minutesColumn = "minutes_played_decimal"
      , windowGames = gamesValue
      , queryLimit = limitValue
      , comparisonEntities = entityValues
      , comparisonRequestedValue = comparisonRequestedFlag
      , resolvedAssumptions = assumptions base
      , joinPath = joinPathValue
      , metricFormula = formula
      , filterLocation = "fact_table"
      }

resolveObjectQuery :: Ontology -> ObjectQuerySpec -> Either Text ResolvedObjectQuery
resolveObjectQuery ontology objectQuery = do
  let base =
        case objectQuery of
          ObjectQuerySpec currentBase _ -> currentBase
  playerGameObject <- maybe (Left "Could not resolve PlayerGame against the ontology.") Right $
    findObject ontology (coreFactObject base)
  playerObject <- maybe (Left "Could not resolve Player against the ontology.") Right $
    findObject ontology (rowObject objectQuery)
  link <- maybe (Left "Could not resolve the PlayerGame -> Player link.") Right $
    findLink ontology "PlayerGame" "Player"
  metricDef <- maybe (Left "Could not resolve total_points against the ontology.") Right $
    findMetric playerGameObject "total_points"
  gamesValue <-
    case filters base of
      [LastNGames n] -> Right n
      _ -> Left "Only a single LastNGames filter is supported."
  let joinPathValue =
        JoinPath
          { factTable = backing_table playerGameObject
          , factJoinKey = source_key link
          , rowTable = backing_table playerObject
          , rowJoinKey = target_key link
          }
  pure
    ResolvedObjectQuery
      { rowTableName = backing_table playerObject
      , factTableName = backing_table playerGameObject
      , rowObjectName = rowObject objectQuery
      , factIdColumn = source_key link
      , rowIdColumn = target_key link
      , playerNameColumn = "player_name"
      , teamColumn = "team"
      , gameDateColumn = "game_date"
      , pointsColumn = "points"
      , minutesColumn = "minutes_played_decimal"
      , windowGames = gamesValue
      , queryLimit = limit base
      , resolvedAssumptions = assumptions base
      , joinPath = joinPathValue
      , metricFormula = resolveMetricFormula metricDef
      , filterLocation = "fact_table"
      }

resolveMetricFormula :: MetricDef -> ResolvedMetricFormula
resolveMetricFormula metricDef =
  ResolvedMetricFormula
    { metricKey = name metricDef
    , aggregationKind = aggregation metricDef
    , sourceAttributes = source_attributes metricDef
    , expressionText = expression metricDef
    , executableInSlice = executable metricDef
    , resultColumn = "metric_value"
    }

resolveEntity :: EntityName -> ResolvedEntity
resolveEntity entityValue =
  case entityValue of
    Brunson -> ResolvedEntity Brunson "Jalen Brunson"
    Haliburton -> ResolvedEntity Haliburton "Tyrese Haliburton"

metricText :: MetricName -> Text
metricText metricValue =
  case metricValue of
    TotalPoints -> "total_points"
    AveragePoints -> "average_points"
    GamesPlayed -> "games_played"
    PointsPer36 -> "points_per_36"
