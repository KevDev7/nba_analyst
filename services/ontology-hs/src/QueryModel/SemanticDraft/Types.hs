{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Types
  ( DraftFilter(..)
  , DraftFreeformObject(..)
  , DraftOrder(..)
  , DraftPredicate(..)
  , DraftTask(..)
  , DraftTimeWindow(..)
  , SemanticDraft(..)
  ) where

import Control.Applicative ((<|>))
import Data.Aeson (FromJSON (parseJSON), Value (Array, Object), withObject, (.:), (.:?), (.!=))
import qualified Data.Aeson.KeyMap as KeyMap
import Data.Aeson.Types (Parser)
import Data.Text (Text)
import qualified QueryModel.IR as QI

data DraftTimeWindow = DraftTimeWindow
  -- The time_window object from the LLM draft.
  -- Example: {"kind":"last_n_games","value":10}.
  { kind :: Text
  , value :: Maybe QI.FilterValue
  }
  deriving (Show, Eq)

instance FromJSON DraftTimeWindow where
  parseJSON = withObject "DraftTimeWindow" $ \obj ->
    DraftTimeWindow
      <$> obj .: "kind"
      <*> obj .:? "value"

data SemanticDraft = SemanticDraft
  -- Haskell's version of the loose JSON draft Python received from the LLM.
  -- These fields stay user-facing; they are not ontology/table/SQL keys yet.
  { task :: Text
  , subject :: Text
  , measure :: Maybe Text
  , measures :: [Text]
  , dimensions :: [Text]
  , filters :: [DraftFilter]
  , resultFilters :: [DraftFilter]
  , predicate :: Maybe DraftPredicate
  , resultPredicate :: Maybe DraftPredicate
  , timeWindow :: DraftTimeWindow
  , grain :: Maybe Text
  , order :: [DraftOrder]
  , limit :: Maybe Int
  , sort :: Maybe Text
  , entities :: [Text]
  , resolvedEntities :: [QI.EntityRef]
  , operations :: [DraftFreeformObject]
  , assumptions :: [Text]
  }
  deriving (Show, Eq)

newtype DraftFreeformObject = DraftFreeformObject ()
  deriving (Show, Eq)

instance FromJSON DraftFreeformObject where
  parseJSON = withObject "DraftFreeformObject" $ \_obj -> pure (DraftFreeformObject ())

data DraftOrder = DraftOrder
  -- A loose user-facing ordering instruction captured by the LLM.
  -- Example: {"by":"game date","direction":"desc"}.
  { orderBy :: Maybe Text
  , orderDirection :: Maybe Text
  }
  deriving (Show, Eq)

instance FromJSON DraftOrder where
  parseJSON = withObject "DraftOrder" $ \obj ->
    DraftOrder
      <$> ((obj .:? "by") <|> (obj .:? "field") <|> (obj .:? "metric") <|> (obj .:? "dimension"))
      <*> ((obj .:? "direction") <|> (obj .:? "sort") <|> (obj .:? "kind"))

data DraftPredicate
  = DraftPredicateLeaf
      { draftPredicateField :: Text
      , draftPredicateOp :: Maybe Text
      , draftPredicateValue :: QI.PredicateValue
      }
  | DraftPredicateAnd [DraftPredicate]
  | DraftPredicateOr [DraftPredicate]
  | DraftPredicateNot DraftPredicate
  deriving (Show, Eq)

instance FromJSON DraftPredicate where
  parseJSON = withObject "DraftPredicate" $ \obj -> do
    kindValue <- obj .: "kind"
    case (kindValue :: Text) of
      "leaf" -> do
        operatorValue <- obj .:? "operator"
        opValue <- obj .:? "op"
        DraftPredicateLeaf
          <$> obj .: "field"
          <*> pure (operatorValue <|> opValue)
          <*> (obj .: "value" >>= parseDraftPredicateValue)
      "and" -> DraftPredicateAnd <$> obj .: "predicates"
      "or" -> DraftPredicateOr <$> obj .: "predicates"
      "not" -> DraftPredicateNot <$> obj .: "predicate"
      _ -> fail ("Unknown draft predicate kind: " <> show kindValue)

parseDraftPredicateValue :: Value -> Parser QI.PredicateValue
parseDraftPredicateValue rawValue =
  case rawValue of
    Object objectValue
      | KeyMap.member "kind" objectValue -> parseJSON rawValue
      | KeyMap.member "lower" objectValue || KeyMap.member "upper" objectValue ->
          withObject "DraftPredicateRangeValue" (\obj -> QI.PredicateRange <$> obj .: "lower" <*> obj .: "upper") rawValue
    Array _ -> QI.PredicateList <$> parseJSON rawValue
    _ -> QI.PredicateScalar <$> parseJSON rawValue

data DraftFilter = DraftFilter
  -- A loose user-facing filter captured by the LLM.
  -- Example: {"field":"season type","op":"=","value":"regular season"}.
  { filterField :: Maybe Text
  , filterOp :: Maybe Text
  , filterValue :: Maybe QI.FilterValue
  }
  deriving (Show, Eq)

instance FromJSON DraftFilter where
  parseJSON = withObject "DraftFilter" $ \obj ->
    DraftFilter
      <$> obj .:? "field"
      <*> obj .:? "op"
      <*> obj .:? "value"

instance FromJSON SemanticDraft where
  parseJSON = withObject "SemanticDraft" $ \obj ->
    SemanticDraft
      <$> obj .: "task"
      <*> obj .: "subject"
      <*> obj .:? "measure"
      <*> obj .:? "measures" .!= []
      <*> obj .:? "dimensions" .!= []
      <*> obj .:? "filters" .!= []
      <*> obj .:? "result_filters" .!= []
      <*> obj .:? "predicate"
      <*> obj .:? "result_predicate"
      <*> obj .: "time_window"
      <*> obj .:? "grain"
      <*> obj .:? "order" .!= []
      <*> obj .:? "limit"
      <*> obj .:? "sort"
      <*> obj .:? "entities" .!= []
      <*> obj .:? "resolved_entities" .!= []
      <*> obj .:? "operations" .!= []
      <*> obj .:? "assumptions" .!= []

data DraftTask
  = DraftRank
  | DraftTrend
  | DraftAggregate
  | DraftFind
  | DraftCompare
  | DraftObject
  | DraftUnknown Text
