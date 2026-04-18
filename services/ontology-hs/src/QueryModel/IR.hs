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

import Control.Applicative ((<|>))
import Data.Aeson
import Data.Aeson.Types (Parser)
import Data.Text (Text)
import GHC.Generics (Generic)

data EntityRef = EntityRef
  { entityId :: Int
  , entityName :: Text
  }
  deriving (Show, Eq, Generic)

instance ToJSON EntityRef where
  toJSON entityRef =
    object
      [ "entityId" .= entityId entityRef
      , "entityName" .= entityName entityRef
      ]

instance FromJSON EntityRef where
  parseJSON = withObject "EntityRef" $ \obj ->
    EntityRef
      <$> obj .: "entityId"
      <*> obj .: "entityName"

type MetricName = Text

type DimensionName = Text

newtype TimeGrain = TimeGrainRef Text
  deriving (Show, Eq, Generic)

monthTimeGrain :: TimeGrain
monthTimeGrain = TimeGrainRef "month"

instance ToJSON TimeGrain where
  toJSON timeGrainValue = String (timeGrainText timeGrainValue)

instance FromJSON TimeGrain where
  parseJSON = withText "TimeGrain" $ \value ->
    if value /= ""
      then pure (TimeGrainRef value)
      else fail "time grains require a non-empty string value."

timeGrainText :: TimeGrain -> Text
timeGrainText timeGrainValue =
  case timeGrainValue of
    TimeGrainRef rawValue -> rawValue

data FilterValue
  = FilterInt Int
  | FilterText Text
  deriving (Show, Eq, Generic)

instance ToJSON FilterValue where
  toJSON filterValue =
    case filterValue of
      FilterInt intValue -> toJSON intValue
      FilterText textValue -> toJSON textValue

instance FromJSON FilterValue where
  parseJSON value =
    (FilterInt <$> parseJSON value) <|> (FilterText <$> parseJSON value)

data Filter
  = FilterRef
      { kind :: Text
      , value :: Maybe FilterValue
      }
  deriving (Show, Eq, Generic)

instance ToJSON Filter where
  toJSON filterValue =
    object $
      ["kind" .= filterKindText filterValue]
        ++ maybe [] (\filterScalar -> ["value" .= filterScalar]) (filterValueRef filterValue)

instance FromJSON Filter where
  parseJSON = withObject "Filter" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "last_n_games" -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        case maybeValue of
          Just (FilterInt gamesValue) | gamesValue > 0 ->
            pure (lastNGamesFilter gamesValue)
          _ -> fail "last_n_games filters require a positive integer value."
      "past_year" -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        case maybeValue of
          Nothing -> pure pastYearFilter
          Just _ -> fail "past_year filters must not provide a value."
      "exact_season" -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        case maybeValue of
          Just (FilterText seasonLabel) | seasonLabel /= ("" :: Text) ->
            pure (exactSeasonFilter seasonLabel)
          _ -> fail "exact_season filters require a non-empty string value."
      "season_type" -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        case maybeValue of
          Just (FilterText seasonTypeLabel) | seasonTypeLabel /= ("" :: Text) ->
            pure (seasonTypeFilter seasonTypeLabel)
          _ -> fail "season_type filters require a non-empty string value."
      _ -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        pure
          FilterRef
            { kind = kindValue
            , value = maybeValue
            }

lastNGamesFilter :: Int -> Filter
lastNGamesFilter gamesValue =
  FilterRef
    { kind = "last_n_games"
    , value = Just (FilterInt gamesValue)
    }

pastYearFilter :: Filter
pastYearFilter =
  FilterRef
    { kind = "past_year"
    , value = Nothing
    }

exactSeasonFilter :: Text -> Filter
exactSeasonFilter seasonLabel =
  FilterRef
    { kind = "exact_season"
    , value = Just (FilterText seasonLabel)
    }

seasonTypeFilter :: Text -> Filter
seasonTypeFilter seasonTypeLabel =
  FilterRef
    { kind = "season_type"
    , value = Just (FilterText seasonTypeLabel)
    }

filterKindText :: Filter -> Text
filterKindText filterValue =
  case filterValue of
    FilterRef {kind = kindValue} -> kindValue

filterValueRef :: Filter -> Maybe FilterValue
filterValueRef filterValue =
  case filterValue of
    FilterRef {value = maybeValue} -> maybeValue

filterIntValue :: Filter -> Maybe Int
filterIntValue filterValue =
  case filterValueRef filterValue of
    Just (FilterInt intValue) -> Just intValue
    _ -> Nothing

filterTextValue :: Filter -> Maybe Text
filterTextValue filterValue =
  case filterValueRef filterValue of
    Just (FilterText textValue) -> Just textValue
    _ -> Nothing

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
  = CompareEntities Text [EntityRef]
  deriving (Show, Eq, Generic)

instance ToJSON ComparisonIntent where
  toJSON (CompareEntities targetObject entities) =
    object
      [ "kind" .= String "compare_entities"
      , "targetObject" .= targetObject
      , "entities" .= entities
      ]

instance FromJSON ComparisonIntent where
  parseJSON = withObject "ComparisonIntent" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "compare_entities" -> CompareEntities <$> obj .: "targetObject" <*> obj .: "entities"
      _ -> fail ("Unknown comparison intent: " <> show kindValue)

data ObjectQuerySpec = ObjectQuerySpec
  { sharedQuery :: BaseQuery
  , rowObject :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data MetricQuerySpec = MetricQuerySpec
  { sharedQuery :: BaseQuery
  , entityFilters :: [EntityRef]
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
