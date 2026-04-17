-- Purpose:
-- Define the typed query IR for the gold-first semantic-layer slices.
--
-- Uses:
-- - matched ontology concepts from earlier query-model modules
--
-- Produces:
-- - the shared Query IR consumed by grounded planning
--
-- Next:
-- - GroundedPlanning/Validation.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.IR where

import Data.Aeson
import Data.Text (Text)
import GHC.Generics (Generic)

data PlayerRef = PlayerRef
  -- Temporary structured comparison ref. This is intentionally narrower than a
  -- full ontology-backed entity reference model, but it removes the fixed
  -- player-id enum and keeps comparison generic over resolved players.
  { personId :: Int
  , playerName :: Text
  }
  deriving (Show, Eq, Generic)

instance ToJSON PlayerRef where
  toJSON playerRef =
    object
      [ "personId" .= personId playerRef
      , "playerName" .= playerName playerRef
      ]

instance FromJSON PlayerRef where
  parseJSON = withObject "PlayerRef" $ \obj ->
    PlayerRef
      <$> obj .: "personId"
      <*> obj .: "playerName"

data MetricName
  = TotalPoints
  | AveragePoints
  | GamesPlayed
  | PointsPer36
  | Wins
  | Losses
  | WinPercentage
  deriving (Show, Eq, Generic)

instance ToJSON MetricName where
  toJSON TotalPoints = String "total_points"
  toJSON AveragePoints = String "average_points"
  toJSON GamesPlayed = String "games_played"
  toJSON PointsPer36 = String "points_per_36"
  toJSON Wins = String "wins"
  toJSON Losses = String "losses"
  toJSON WinPercentage = String "win_percentage"

instance FromJSON MetricName where
  parseJSON = withText "MetricName" $ \value ->
    case value of
      "total_points" -> pure TotalPoints
      "average_points" -> pure AveragePoints
      "games_played" -> pure GamesPlayed
      "points_per_36" -> pure PointsPer36
      "wins" -> pure Wins
      "losses" -> pure Losses
      "win_percentage" -> pure WinPercentage
      _ -> fail ("Unknown metric: " <> show value)

data DimensionName
  = PlayerName
  | TeamName
  | DisplayName
  | Team
  | PrimaryPosition
  deriving (Show, Eq, Generic)

instance ToJSON DimensionName where
  toJSON PlayerName = String "player_name"
  toJSON TeamName = String "team_name"
  toJSON DisplayName = String "display_name"
  toJSON Team = String "team"
  toJSON PrimaryPosition = String "primary_position"

instance FromJSON DimensionName where
  parseJSON = withText "DimensionName" $ \value ->
    case value of
      "player_name" -> pure PlayerName
      "team_name" -> pure TeamName
      "display_name" -> pure DisplayName
      "team" -> pure Team
      "primary_position" -> pure PrimaryPosition
      _ -> fail ("Unknown dimension: " <> show value)

data TimeGrain
  = Month
  deriving (Show, Eq, Generic)

instance ToJSON TimeGrain where
  toJSON Month = String "month"

instance FromJSON TimeGrain where
  parseJSON = withText "TimeGrain" $ \value ->
    case value of
      "month" -> pure Month
      _ -> fail ("Unknown time grain: " <> show value)

data Filter
  = LastNGames Int
  | PastYear
  | ExactSeason Text
  | SeasonTypeFilter Text
  deriving (Show, Eq, Generic)

instance ToJSON Filter where
  toJSON (LastNGames n) = object ["kind" .= String "last_n_games", "value" .= n]
  toJSON PastYear = object ["kind" .= String "past_year"]
  toJSON (ExactSeason seasonLabel) =
    object ["kind" .= String "exact_season", "value" .= seasonLabel]
  toJSON (SeasonTypeFilter seasonTypeLabel) =
    object ["kind" .= String "season_type", "value" .= seasonTypeLabel]

instance FromJSON Filter where
  parseJSON = withObject "Filter" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "last_n_games" -> LastNGames <$> obj .: "value"
      "past_year" -> pure PastYear
      "exact_season" -> ExactSeason <$> obj .: "value"
      "season_type" -> SeasonTypeFilter <$> obj .: "value"
      _ -> fail ("Unknown filter kind: " <> show kindValue)

data Order
  = Desc MetricName
  deriving (Show, Eq, Generic)

instance ToJSON Order where
  toJSON (Desc metricName) = object ["kind" .= String "desc", "metric" .= metricName]

instance FromJSON Order where
  parseJSON = withObject "Order" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "desc" -> Desc <$> obj .: "metric"
      _ -> fail ("Unknown order kind: " <> show kindValue)

data LinkedFilter = LinkedFilter
  { targetObject :: Text
  , attribute :: Text
  , value :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data BaseQuery = BaseQuery
  { coreFactObject :: Text
  , metrics :: [MetricName]
  , dimensions :: [DimensionName]
  , timeGrain :: Maybe TimeGrain
  , filters :: [Filter]
  , linkedFilters :: [LinkedFilter]
  , orders :: [Order]
  , limit :: Maybe Int
  , assumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ComparisonIntent
  = CompareEntities [PlayerRef]
  deriving (Show, Eq, Generic)

instance ToJSON ComparisonIntent where
  toJSON (CompareEntities entities) =
    object ["kind" .= String "compare_entities", "entities" .= entities]

instance FromJSON ComparisonIntent where
  parseJSON = withObject "ComparisonIntent" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "compare_entities" -> CompareEntities <$> obj .: "entities"
      _ -> fail ("Unknown comparison intent: " <> show kindValue)

data ObjectQuerySpec = ObjectQuerySpec
  { sharedQuery :: BaseQuery
  , rowObject :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data MetricQuerySpec = MetricQuerySpec
  { sharedQuery :: BaseQuery
  , entityFilters :: [PlayerRef]
  , comparison :: Maybe ComparisonIntent
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data Query
  = ObjectQuery ObjectQuerySpec
  | MetricQuery MetricQuerySpec
  deriving (Show, Eq, Generic)

instance ToJSON Query where
  toJSON (ObjectQuery spec) = object ["kind" .= String "object_query", "spec" .= spec]
  toJSON (MetricQuery spec) = object ["kind" .= String "metric_query", "spec" .= spec]

instance FromJSON Query where
  parseJSON = withObject "Query" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "object_query" -> ObjectQuery <$> obj .: "spec"
      "metric_query" -> MetricQuery <$> obj .: "spec"
      _ -> fail ("Unknown query kind: " <> show kindValue)
