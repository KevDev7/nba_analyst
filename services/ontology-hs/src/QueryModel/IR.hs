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

data EntityName
  = Brunson
  | Haliburton
  deriving (Show, Eq, Generic)

instance ToJSON EntityName where
  toJSON Brunson = String "jalen_brunson"
  toJSON Haliburton = String "tyrese_haliburton"

instance FromJSON EntityName where
  parseJSON = withText "EntityName" $ \value ->
    case value of
      "jalen_brunson" -> pure Brunson
      "tyrese_haliburton" -> pure Haliburton
      _ -> fail ("Unknown entity: " <> show value)

data MetricName
  = TotalPoints
  | AveragePoints
  | GamesPlayed
  | PointsPer36
  deriving (Show, Eq, Generic)

instance ToJSON MetricName where
  toJSON TotalPoints = String "total_points"
  toJSON AveragePoints = String "average_points"
  toJSON GamesPlayed = String "games_played"
  toJSON PointsPer36 = String "points_per_36"

instance FromJSON MetricName where
  parseJSON = withText "MetricName" $ \value ->
    case value of
      "total_points" -> pure TotalPoints
      "average_points" -> pure AveragePoints
      "games_played" -> pure GamesPlayed
      "points_per_36" -> pure PointsPer36
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

data Filter
  = LastNGames Int
  deriving (Show, Eq, Generic)

instance ToJSON Filter where
  toJSON (LastNGames n) = object ["kind" .= String "last_n_games", "value" .= n]

instance FromJSON Filter where
  parseJSON = withObject "Filter" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "last_n_games" -> LastNGames <$> obj .: "value"
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

data BaseQuery = BaseQuery
  { coreFactObject :: Text
  , metrics :: [MetricName]
  , dimensions :: [DimensionName]
  , filters :: [Filter]
  , orders :: [Order]
  , limit :: Maybe Int
  , assumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ComparisonIntent
  = CompareEntities [EntityName]
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
  , entityFilters :: [EntityName]
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
