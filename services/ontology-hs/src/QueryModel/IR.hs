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
import Data.Maybe (catMaybes)
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

data FindDisplaySpec = FindDisplaySpec
  { findDisplayAttribute :: DimensionName
  , findDisplayTargetObject :: Maybe Text
  , findDisplayLinkRole :: Maybe Text
  , findDisplayLabel :: Maybe Text
  }
  deriving (Show, Eq, Generic)

instance ToJSON FindDisplaySpec where
  toJSON displaySpec =
    case displaySpec of
      FindDisplaySpec attributeValue Nothing Nothing Nothing -> String attributeValue
      FindDisplaySpec attributeValue maybeTargetObject maybeLinkRole maybeLabel ->
        object
          [ "attribute" .= attributeValue
          , "targetObject" .= maybeTargetObject
          , "linkRole" .= maybeLinkRole
          , "label" .= maybeLabel
          ]

instance FromJSON FindDisplaySpec where
  parseJSON value =
    (withText "FindDisplaySpec" (\attributeValue -> pure (simpleFindDisplaySpec attributeValue)) value)
      <|> withObject
        "FindDisplaySpec"
        ( \obj ->
            FindDisplaySpec
              <$> obj .: "attribute"
              <*> obj .:? "targetObject"
              <*> obj .:? "linkRole"
              <*> obj .:? "label"
        )
        value

simpleFindDisplaySpec :: DimensionName -> FindDisplaySpec
simpleFindDisplaySpec attributeValue =
  FindDisplaySpec
    { findDisplayAttribute = attributeValue
    , findDisplayTargetObject = Nothing
    , findDisplayLinkRole = Nothing
    , findDisplayLabel = Nothing
    }

data FindOrderDirection
  = FindOrderAsc
  | FindOrderDesc
  deriving (Show, Eq, Generic)

instance ToJSON FindOrderDirection where
  toJSON directionValue =
    String $
      case directionValue of
        FindOrderAsc -> "asc"
        FindOrderDesc -> "desc"

instance FromJSON FindOrderDirection where
  parseJSON = withText "FindOrderDirection" $ \value ->
    case value of
      "asc" -> pure FindOrderAsc
      "ascending" -> pure FindOrderAsc
      "oldest" -> pure FindOrderAsc
      "desc" -> pure FindOrderDesc
      "descending" -> pure FindOrderDesc
      "newest" -> pure FindOrderDesc
      _ -> fail ("Unknown find order direction: " <> show value)

data FindOrderSpec = FindOrderSpec
  { findOrderField :: FindDisplaySpec
  , findOrderDirection :: FindOrderDirection
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

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
  | FilterDouble Double
  | FilterText Text
  deriving (Show, Eq, Generic)

instance ToJSON FilterValue where
  toJSON filterValue =
    case filterValue of
      FilterInt intValue -> toJSON intValue
      FilterDouble doubleValue -> toJSON doubleValue
      FilterText textValue -> toJSON textValue

instance FromJSON FilterValue where
  parseJSON value =
    (FilterInt <$> parseJSON value) <|> (FilterDouble <$> parseJSON value) <|> (FilterText <$> parseJSON value)

-- A predicate field is a future-proof reference to a grounded ontology field.
-- Plain English: which object's attribute is being filtered, and is that
-- filter applied before grouping (row) or after grouping (result)?
data PredicateFieldLocation
  = PredicateRowField
  | PredicateResultField
  deriving (Show, Eq, Generic)

instance ToJSON PredicateFieldLocation where
  toJSON locationValue =
    String $
      case locationValue of
        PredicateRowField -> "row"
        PredicateResultField -> "result"

instance FromJSON PredicateFieldLocation where
  parseJSON = withText "PredicateFieldLocation" $ \value ->
    case value of
      "row" -> pure PredicateRowField
      "result" -> pure PredicateResultField
      _ -> fail ("Unknown predicate field location: " <> show value)

data PredicateField = PredicateField
  { predicateFieldTargetObject :: Text
  , predicateFieldAttribute :: Text
  , predicateLocation :: PredicateFieldLocation
  , predicateFieldLinkRole :: Maybe Text
  , predicateFieldLabel :: Maybe Text
  }
  deriving (Show, Eq, Generic)

instance ToJSON PredicateField where
  toJSON fieldValue =
    object $
      [ "targetObject" .= predicateFieldTargetObject fieldValue
      , "attribute" .= predicateFieldAttribute fieldValue
      , "location" .= predicateLocation fieldValue
      ]
        <> catMaybes
          [ ("linkRole" .=) <$> predicateFieldLinkRole fieldValue
          , ("label" .=) <$> predicateFieldLabel fieldValue
          ]

instance FromJSON PredicateField where
  parseJSON = withObject "PredicateField" $ \obj ->
    PredicateField
      <$> obj .: "targetObject"
      <*> obj .: "attribute"
      <*> obj .: "location"
      <*> obj .:? "linkRole"
      <*> obj .:? "label"

data PredicateOperator
  = PredicateEquals
  | PredicateNotEquals
  | PredicateGreaterThan
  | PredicateGreaterThanOrEqual
  | PredicateLessThan
  | PredicateLessThanOrEqual
  | PredicateIn
  | PredicateNotIn
  | PredicateBetween
  | PredicateContains
  deriving (Show, Eq, Generic)

instance ToJSON PredicateOperator where
  toJSON operatorValue =
    String $
      case operatorValue of
        PredicateEquals -> "equals"
        PredicateNotEquals -> "not_equals"
        PredicateGreaterThan -> "greater_than"
        PredicateGreaterThanOrEqual -> "greater_than_or_equal"
        PredicateLessThan -> "less_than"
        PredicateLessThanOrEqual -> "less_than_or_equal"
        PredicateIn -> "in"
        PredicateNotIn -> "not_in"
        PredicateBetween -> "between"
        PredicateContains -> "contains"

instance FromJSON PredicateOperator where
  parseJSON = withText "PredicateOperator" $ \value ->
    case value of
      "=" -> pure PredicateEquals
      "equals" -> pure PredicateEquals
      "eq" -> pure PredicateEquals
      "!=" -> pure PredicateNotEquals
      "<>" -> pure PredicateNotEquals
      "not_equals" -> pure PredicateNotEquals
      "neq" -> pure PredicateNotEquals
      ">" -> pure PredicateGreaterThan
      "greater_than" -> pure PredicateGreaterThan
      "gt" -> pure PredicateGreaterThan
      ">=" -> pure PredicateGreaterThanOrEqual
      "greater_than_or_equal" -> pure PredicateGreaterThanOrEqual
      "gte" -> pure PredicateGreaterThanOrEqual
      "<" -> pure PredicateLessThan
      "less_than" -> pure PredicateLessThan
      "lt" -> pure PredicateLessThan
      "<=" -> pure PredicateLessThanOrEqual
      "less_than_or_equal" -> pure PredicateLessThanOrEqual
      "lte" -> pure PredicateLessThanOrEqual
      "in" -> pure PredicateIn
      "not_in" -> pure PredicateNotIn
      "between" -> pure PredicateBetween
      "contains" -> pure PredicateContains
      _ -> fail ("Unknown predicate operator: " <> show value)

predicateOperatorText :: PredicateOperator -> Text
predicateOperatorText operatorValue =
  case operatorValue of
    PredicateEquals -> "="
    PredicateNotEquals -> "<>"
    PredicateGreaterThan -> ">"
    PredicateGreaterThanOrEqual -> ">="
    PredicateLessThan -> "<"
    PredicateLessThanOrEqual -> "<="
    PredicateIn -> "in"
    PredicateNotIn -> "not_in"
    PredicateBetween -> "between"
    PredicateContains -> "contains"

data PredicateValue
  = PredicateScalar FilterValue
  | PredicateList [FilterValue]
  | PredicateRange FilterValue FilterValue
  deriving (Show, Eq, Generic)

instance ToJSON PredicateValue where
  toJSON value =
    case value of
      PredicateScalar scalarValue ->
        object
          [ "kind" .= String "scalar"
          , "value" .= scalarValue
          ]
      PredicateList listValues ->
        object
          [ "kind" .= String "list"
          , "values" .= listValues
          ]
      PredicateRange lowerValue upperValue ->
        object
          [ "kind" .= String "range"
          , "lower" .= lowerValue
          , "upper" .= upperValue
          ]

instance FromJSON PredicateValue where
  parseJSON = withObject "PredicateValue" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "scalar" -> PredicateScalar <$> obj .: "value"
      "list" -> PredicateList <$> obj .: "values"
      "range" -> PredicateRange <$> obj .: "lower" <*> obj .: "upper"
      _ -> fail ("Unknown predicate value kind: " <> show kindValue)

data Predicate
  = PredicateLeaf PredicateField PredicateOperator PredicateValue
  | PredicateAnd [Predicate]
  | PredicateOr [Predicate]
  | PredicateNot Predicate
  deriving (Show, Eq, Generic)

instance ToJSON Predicate where
  toJSON predicateValue =
    case predicateValue of
      PredicateLeaf fieldValue operatorValue valueValue ->
        object
          [ "kind" .= String "leaf"
          , "field" .= fieldValue
          , "operator" .= operatorValue
          , "value" .= valueValue
          ]
      PredicateAnd predicateValues ->
        object
          [ "kind" .= String "and"
          , "predicates" .= predicateValues
          ]
      PredicateOr predicateValues ->
        object
          [ "kind" .= String "or"
          , "predicates" .= predicateValues
          ]
      PredicateNot nestedPredicate ->
        object
          [ "kind" .= String "not"
          , "predicate" .= nestedPredicate
          ]

instance FromJSON Predicate where
  parseJSON = withObject "Predicate" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "leaf" -> PredicateLeaf <$> obj .: "field" <*> obj .: "operator" <*> obj .: "value"
      "and" -> PredicateAnd <$> obj .: "predicates"
      "or" -> PredicateOr <$> obj .: "predicates"
      "not" -> PredicateNot <$> obj .: "predicate"
      _ -> fail ("Unknown predicate kind: " <> show kindValue)

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
      "last_n_days" -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        case maybeValue of
          Just (FilterInt daysValue) | daysValue > 0 ->
            pure (lastNDaysFilter daysValue)
          _ -> fail "last_n_days filters require a positive integer value."
      "past_year" -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        case maybeValue of
          Nothing -> pure pastYearFilter
          Just _ -> fail "past_year filters must not provide a value."
      "date_from" -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        case maybeValue of
          Just (FilterText startDate) | startDate /= ("" :: Text) ->
            pure (dateFromFilter startDate)
          _ -> fail "date_from filters require a non-empty string value."
      "date_to" -> do
        maybeValue <- obj .:? "value" :: Parser (Maybe FilterValue)
        case maybeValue of
          Just (FilterText endDate) | endDate /= ("" :: Text) ->
            pure (dateToFilter endDate)
          _ -> fail "date_to filters require a non-empty string value."
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

-- Build the canonical IR shape for "last N calendar days".
lastNDaysFilter :: Int -> Filter
lastNDaysFilter daysValue =
  FilterRef
    { kind = "last_n_days"
    , value = Just (FilterInt daysValue)
    }

-- Build the canonical IR shape for "past year".
pastYearFilter :: Filter
pastYearFilter =
  FilterRef
    { kind = "past_year"
    , value = Nothing
    }

-- Build the canonical IR shape for an inclusive lower game-date bound.
dateFromFilter :: Text -> Filter
dateFromFilter startDate =
  FilterRef
    { kind = "date_from"
    , value = Just (FilterText startDate)
    }

-- Build the canonical IR shape for an inclusive upper game-date bound.
dateToFilter :: Text -> Filter
dateToFilter endDate =
  FilterRef
    { kind = "date_to"
    , value = Just (FilterText endDate)
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

-- The shared body of both object queries and metric queries.
-- Plain English: what table/object is the query centered on, what measurements
-- and breakdowns are involved, what filters apply, and how should results sort.
data BaseQuery = BaseQuery
  { coreFactObject :: Text
  , metrics :: [MetricName]
  , dimensions :: [DimensionName]
  , timeGrain :: Maybe TimeGrain
  , filters :: [Filter]
  , rowPredicate :: Maybe Predicate
  , resultPredicate :: Maybe Predicate
  , orders :: [Order]
  , limit :: Maybe Int
  , assumptions :: [Text]
  }
  deriving (Show, Eq, Generic)

instance ToJSON BaseQuery where
  toJSON base =
    object
      [ "coreFactObject" .= coreFactObject base
      , "metrics" .= metrics base
      , "dimensions" .= dimensions base
      , "timeGrain" .= timeGrain base
      , "filters" .= filters base
      , "rowPredicate" .= rowPredicate base
      , "resultPredicate" .= resultPredicate base
      , "orders" .= orders base
      , "limit" .= limit base
      , "assumptions" .= assumptions base
      ]

instance FromJSON BaseQuery where
  parseJSON = withObject "BaseQuery" $ \obj ->
    BaseQuery
      <$> obj .: "coreFactObject"
      <*> obj .: "metrics"
      <*> obj .: "dimensions"
      <*> obj .:? "timeGrain"
      <*> obj .: "filters"
      <*> obj .:? "rowPredicate"
      <*> obj .:? "resultPredicate"
      <*> obj .: "orders"
      <*> obj .:? "limit"
      <*> obj .:? "assumptions" .!= []

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
  , rankIntentLabel :: Maybe Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data FindQuerySpec = FindQuerySpec
  { findCoreFactObject :: Text
  , findTargetObject :: Text
  , findDisplayDimensions :: [FindDisplaySpec]
  , findOrders :: [FindOrderSpec]
  , findPredicateTree :: Maybe Predicate
  , findFilters :: [Filter]
  , findLimit :: Maybe Int
  , findAssumptions :: [Text]
  }
  deriving (Show, Eq, Generic, ToJSON)

instance FromJSON FindQuerySpec where
  parseJSON = withObject "FindQuerySpec" $ \obj ->
    FindQuerySpec
      <$> obj .: "findCoreFactObject"
      <*> obj .: "findTargetObject"
      <*> obj .: "findDisplayDimensions"
      <*> obj .:? "findOrders" .!= []
      <*> obj .:? "findPredicateTree"
      <*> obj .: "findFilters"
      <*> obj .:? "findLimit"
      <*> obj .:? "findAssumptions" .!= []

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
