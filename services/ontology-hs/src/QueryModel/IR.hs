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

-- A specific real-world entity the query cares about, like one player.
-- Example: entityId = 1628973, entityName = "Jalen Brunson".
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

-- These are semantic names, not raw database column names.
-- Grounded planning later proves they exist in the ontology before SQL is built.
type MetricName = Text

type DimensionName = Text

-- A time bucket for trend-style answers, like "month".
newtype TimeGrain = TimeGrainRef Text
  deriving (Show, Eq, Generic)

-- Convenience value for monthly trend queries.
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

-- A filter value can be either a number or text.
-- Example: last_n_games uses FilterInt 10, exact_season uses FilterText "2024-25".
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

-- A named constraint on the query.
-- Example: kind = "last_n_games", value = 10 means "only use the last 10 games."
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
      -- Some filter kinds get extra validation here so malformed JSON fails early.
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

-- Build the canonical IR shape for "last N games" instead of repeating strings.
lastNGamesFilter :: Int -> Filter
lastNGamesFilter gamesValue =
  FilterRef
    { kind = "last_n_games"
    , value = Just (FilterInt gamesValue)
    }

-- Build the canonical IR shape for "past year".
pastYearFilter :: Filter
pastYearFilter =
  FilterRef
    { kind = "past_year"
    , value = Nothing
    }

-- Build the canonical IR shape for a specific season label.
exactSeasonFilter :: Text -> Filter
exactSeasonFilter seasonLabel =
  FilterRef
    { kind = "exact_season"
    , value = Just (FilterText seasonLabel)
    }

-- Build the canonical IR shape for regular season, playoffs, etc.
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

-- Sorting instructions for the final answer.
-- Example: "top players by points" sorts descending; "bottom teams by wins"
-- sorts ascending.
data Order
  = Asc MetricName
  | Desc MetricName
  deriving (Show, Eq, Generic)

instance ToJSON Order where
  toJSON (Asc metricName) = object ["kind" .= String "asc", "metric" .= metricName]
  toJSON (Desc metricName) = object ["kind" .= String "desc", "metric" .= metricName]

instance FromJSON Order where
  parseJSON = withObject "Order" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "asc" -> Asc <$> obj .: "metric"
      "desc" -> Desc <$> obj .: "metric"
      _ -> fail ("Unknown order kind: " <> show kindValue)

-- A filter that reaches through a relationship to another object.
-- Example: filter PlayerGame rows by a Player attribute such as full_name.
data LinkedFilter = LinkedFilter
  { targetObject :: Text
  , attribute :: Text
  , value :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PredicateOp
  = OpEq
  | OpGt
  | OpGte
  | OpLt
  | OpLte
  deriving (Show, Eq, Generic)

instance ToJSON PredicateOp where
  toJSON opValue =
    String $
      case opValue of
        OpEq -> "="
        OpGt -> ">"
        OpGte -> ">="
        OpLt -> "<"
        OpLte -> "<="

instance FromJSON PredicateOp where
  parseJSON = withText "PredicateOp" $ \value ->
    case value of
      "=" -> pure OpEq
      "eq" -> pure OpEq
      ">" -> pure OpGt
      "gt" -> pure OpGt
      ">=" -> pure OpGte
      "gte" -> pure OpGte
      "<" -> pure OpLt
      "lt" -> pure OpLt
      "<=" -> pure OpLte
      "lte" -> pure OpLte
      _ -> fail ("Unknown predicate operator: " <> show value)

predicateOpText :: PredicateOp -> Text
predicateOpText opValue =
  case opValue of
    OpEq -> "="
    OpGt -> ">"
    OpGte -> ">="
    OpLt -> "<"
    OpLte -> "<="

data FindPredicate = FindPredicate
  { predicateTargetObject :: Text
  , predicateAttribute :: Text
  , predicateOperator :: PredicateOp
  , predicateFilterValue :: FilterValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

-- The shared body of both object queries and metric queries.
-- Plain English: what table/object is the query centered on, what measurements
-- and breakdowns are involved, what filters apply, and how should results sort.
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

-- Extra intent for questions that compare named entities.
-- Example: "compare Brunson and Haliburton" points at two player entities.
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

-- Object query = each answer row is mainly an entity.
-- Example: "show players with their teams" is about rows of players.
data ObjectQuerySpec = ObjectQuerySpec
  { sharedQuery :: BaseQuery
  , rowObject :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

-- Metric query = each answer row is mainly a measurement/breakdown.
-- Example: "top 10 players by points" is about a points metric grouped by player.
data MetricQuerySpec = MetricQuerySpec
  { sharedQuery :: BaseQuery
  , entityFilters :: [EntityRef]
  , comparison :: Maybe ComparisonIntent
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data FindQuerySpec = FindQuerySpec
  { findCoreFactObject :: Text
  , findTargetObject :: Text
  , findDisplayDimensions :: [DimensionName]
  , findPredicates :: [FindPredicate]
  , findFilters :: [Filter]
  , findLimit :: Maybe Int
  , findAssumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

-- The top-level fork in the query model.
-- By this point the messy language is gone; Haskell sees either an ObjectQuery
-- or a MetricQuery with typed fields.
data Query
  = ObjectQuery ObjectQuerySpec
  | MetricQuery MetricQuerySpec
  | FindQuery FindQuerySpec
  deriving (Show, Eq, Generic)

instance ToJSON Query where
  toJSON (ObjectQuery spec) = object ["kind" .= String "object_query", "spec" .= spec]
  toJSON (MetricQuery spec) = object ["kind" .= String "metric_query", "spec" .= spec]
  toJSON (FindQuery spec) = object ["kind" .= String "find_query", "spec" .= spec]

instance FromJSON Query where
  parseJSON = withObject "Query" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "object_query" -> ObjectQuery <$> obj .: "spec"
      "metric_query" -> MetricQuery <$> obj .: "spec"
      "find_query" -> FindQuery <$> obj .: "spec"
      _ -> fail ("Unknown query kind: " <> show kindValue)
