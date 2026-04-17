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

data ColumnRef = ColumnRef
  { tableRole :: Text
  , columnName :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ContextJoin = ContextJoin
  { contextTableName :: Text
  , factContextKey :: Text
  , contextRowKey :: Text
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
  , rowObjectName :: Text
  , factIdColumn :: Text
  , rowIdColumn :: Text
  , contextJoin :: Maybe ContextJoin
  , displayName :: ColumnRef
  , contextValue :: Maybe ColumnRef
  , gameDate :: ColumnRef
  , metricSource :: ColumnRef
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
  , contextJoin :: Maybe ContextJoin
  , displayName :: ColumnRef
  , contextValue :: Maybe ColumnRef
  , gameDate :: ColumnRef
  , metricSource :: ColumnRef
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
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- maybe (Left "Could not resolve the fact object against the ontology.") Right $
    findObject ontology (coreFactObject base)
  rowObjectNameValue <- metricRowObjectName (dimensions base)
  rowObject <- maybe (Left "Could not resolve the row object against the ontology.") Right $
    findObject ontology rowObjectNameValue
  link <- maybe (Left "Could not resolve the fact-to-row link.") Right $
    findLink ontology (coreFactObject base) rowObjectNameValue
  selectedMetric <- requireSingleMetric (metrics base)
  metricDef <- maybe (Left "Could not resolve the selected metric against the ontology.") Right $
    findMetric factObject (metricText selectedMetric)
  gamesValue <- requireLastNGames (filters base)
  displayColumn <- metricDisplayColumn (dimensions base)
  (contextJoinValue, contextColumn) <- metricContextSelection ontology (coreFactObject base)
  metricSourceColumn <- metricSourceAttribute metricDef
  let limitValue = limit base
      entityValues = map resolveEntity (entityFilters metricQuery)
      comparisonRequestedFlag =
        case comparison metricQuery of
          Just _ -> True
          Nothing -> False
      joinPathValue =
        JoinPath
          { factTable = backing_table factObject
          , factJoinKey = source_key link
          , rowTable = backing_table rowObject
          , rowJoinKey = target_key link
          }
      formula = resolveMetricFormula metricDef
  pure
    ResolvedMetricQuery
      { factTableName = backing_table factObject
      , rowTableName = backing_table rowObject
      , rowObjectName = rowObjectNameValue
      , factIdColumn = source_key link
      , rowIdColumn = target_key link
      , contextJoin = contextJoinValue
      , displayName = ColumnRef "row" displayColumn
      , contextValue = contextColumn
      , gameDate = ColumnRef "fact" "game_date"
      , metricSource = ColumnRef "fact" metricSourceColumn
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
          ObjectQuerySpec {sharedQuery = currentBase} -> currentBase
      rowObjectNameValue =
        case objectQuery of
          ObjectQuerySpec {rowObject = currentRowObject} -> currentRowObject
  factObject <- maybe (Left "Could not resolve the fact object against the ontology.") Right $
    findObject ontology (coreFactObject base)
  rowObjectValue <- maybe (Left "Could not resolve the row object against the ontology.") Right $
    findObject ontology rowObjectNameValue
  link <- maybe (Left "Could not resolve the fact-to-row link.") Right $
    findLink ontology (coreFactObject base) rowObjectNameValue
  metricDef <- maybe (Left "Could not resolve total_points against the ontology.") Right $
    findMetric factObject "total_points"
  gamesValue <- requireLastNGames (filters base)
  displayColumn <- metricDisplayColumn (dimensions base)
  (contextJoinValue, contextColumn) <- metricContextSelection ontology (coreFactObject base)
  metricSourceColumn <- metricSourceAttribute metricDef
  pure
    ResolvedObjectQuery
      { rowTableName = backing_table rowObjectValue
      , factTableName = backing_table factObject
      , rowObjectName = rowObjectNameValue
      , factIdColumn = source_key link
      , rowIdColumn = target_key link
      , contextJoin = contextJoinValue
      , displayName = ColumnRef "row" displayColumn
      , contextValue = contextColumn
      , gameDate = ColumnRef "fact" "game_date"
      , metricSource = ColumnRef "fact" metricSourceColumn
      , windowGames = gamesValue
      , queryLimit = limit base
      , resolvedAssumptions = assumptions base
      , joinPath =
          JoinPath
            { factTable = backing_table factObject
            , factJoinKey = source_key link
            , rowTable = backing_table rowObjectValue
            , rowJoinKey = target_key link
            }
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

metricRowObjectName :: [DimensionName] -> Either Text Text
metricRowObjectName dimensionValues =
  case dimensionValues of
    [PlayerName] -> Right "Player"
    [TeamName] -> Right "Team"
    _ -> Left "Only player_name or team_name metric dimensions are supported in this slice."

metricDisplayColumn :: [DimensionName] -> Either Text Text
metricDisplayColumn dimensionValues =
  case dimensionValues of
    [PlayerName] -> Right "player_name"
    [TeamName] -> Right "team_name"
    _ -> Left "Only player_name or team_name metric dimensions are supported in this slice."

metricContextSelection :: Ontology -> Text -> Either Text (Maybe ContextJoin, Maybe ColumnRef)
metricContextSelection ontology factObjectName =
  case factObjectName of
    "PlayerGame" -> do
      teamObject <- maybe (Left "Could not resolve Team against the ontology.") Right $
        findObject ontology "Team"
      link <- maybe (Left "Could not resolve the PlayerGame -> Team link.") Right $
        findLink ontology "PlayerGame" "Team"
      Right
        ( Just
            ContextJoin
              { contextTableName = backing_table teamObject
              , factContextKey = source_key link
              , contextRowKey = target_key link
              }
        , Just (ColumnRef "context" "team_abbreviation")
        )
    "TeamGame" -> Right (Nothing, Just (ColumnRef "fact" "team_abbreviation"))
    _ -> Left "Unsupported fact object for ranking context."

metricSourceAttribute :: MetricDef -> Either Text Text
metricSourceAttribute metricDef =
  case source_attributes metricDef of
    sourceAttribute : _ -> Right sourceAttribute
    [] -> Left "Selected metric must reference at least one source attribute."

requireSingleMetric :: [MetricName] -> Either Text MetricName
requireSingleMetric metricValues =
  case metricValues of
    [metricValue] -> Right metricValue
    _ -> Left "Query requires exactly one selected metric."

requireLastNGames :: [Filter] -> Either Text Int
requireLastNGames filterValues =
  case filterValues of
    [LastNGames n] -> Right n
    _ -> Left "Only a single LastNGames filter is supported."
