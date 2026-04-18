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

type MetricName = Text

type DimensionName = Text

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
