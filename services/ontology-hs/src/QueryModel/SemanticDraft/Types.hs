{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Types
  ( DraftFilter(..)
  , DraftFreeformObject(..)
  , DraftOrder(..)
  , DraftPredicate(..)
  , DraftTask(..)
  , DraftTimeWindow(..)
  , GroundedAggregate(..)
  , GroundedComparison(..)
  , GroundedFind(..)
  , GroundedRanking(..)
  , GroundedTrend(..)
  , SemanticDraft(..)
  , SemanticGroupingDimension(..)
  , TimeScope(..)
  ) where

import Control.Applicative ((<|>))
import Data.Aeson (FromJSON (parseJSON), Value (Array, Object), withObject, (.:), (.:?), (.!=))
import qualified Data.Aeson.KeyMap as KeyMap
import Data.Aeson.Types (Parser)
import Data.Text (Text)
import OntologyLayer.Types (Object)
import qualified OntologyLayer.Types as OT
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

data GroundedRanking = GroundedRanking
  -- A ranking draft after it has been grounded against the ontology.
  -- At this point we know the real fact object, subject object, metric, and
  -- display dimension needed to build typed Query IR.
  { factObject :: Object
  , subjectObject :: Object
  , metricDef :: OT.MetricDef
  , metricDefs :: [OT.MetricDef]
  , displayDimension :: Text
  , displayDimensions :: [Text]
  , filterValues :: [QI.Filter]
  , rowPredicateValue :: Maybe QI.Predicate
  , resultPredicateValue :: Maybe QI.Predicate
  , limitValue :: Maybe Int
  , assumptionValues :: [Text]
  , matchScore :: Int
  , subjectAffinityScore :: Int
  }

data TimeScope
  = RecentGames Int [QI.Filter]
  | LastNDays Int
  | ExactSeason Text Text
  | SeasonTypeOnly Text
  | PastYear
  | DateRange (Maybe Text) (Maybe Text)
  | AllAvailable
  deriving (Show, Eq)

data GroundedTrend = GroundedTrend
  -- A trend draft after ontology grounding.
  -- It identifies the fact surface, metric, optional series dimension, grain,
  -- and filters needed to build a typed time-series Query IR.
  { trendFactObject :: Object
  , trendMetricDef :: OT.MetricDef
  , trendMetricDefs :: [OT.MetricDef]
  , trendDisplayDimensions :: [Text]
  , trendGrainValue :: Text
  , trendFilterValues :: [QI.Filter]
  , trendRowPredicateValue :: Maybe QI.Predicate
  , trendResultPredicateValue :: Maybe QI.Predicate
  , trendAssumptions :: [Text]
  , trendMatchScore :: Int
  , trendSubjectAffinityScore :: Int
  }

data GroundedComparison = GroundedComparison
  -- A comparison draft after data-backed entity names have been grounded and
  -- the ontology has selected a fact object, metric, and identity dimension.
  { comparisonFactObject :: Object
  , comparisonSubjectObject :: Object
  , comparisonMetricDef :: OT.MetricDef
  , comparisonMetricDefs :: [OT.MetricDef]
  , comparisonDisplayDimension :: Text
  , comparisonDisplayDimensions :: [Text]
  , comparisonGrainValue :: Maybe Text
  , comparisonFilterValues :: [QI.Filter]
  , comparisonRowPredicateValue :: Maybe QI.Predicate
  , comparisonEntitiesValue :: [QI.EntityRef]
  , comparisonAssumptions :: [Text]
  , comparisonMatchScore :: Int
  , comparisonSubjectAffinityScore :: Int
  }

data SemanticGroupingDimension = SemanticGroupingDimension
  { groupingDimensionObject :: Object
  , groupingDimensionName :: Text
  }

data GroundedAggregate = GroundedAggregate
  -- An aggregate draft after ontology grounding.
  -- It identifies the fact surface, metric, and public grouping dimensions
  -- needed to build grouped metric-query IR without adding a ranking shape.
  { aggregateFactObject :: Object
  , aggregateGroupObjects :: [Object]
  , aggregateMetricDef :: OT.MetricDef
  , aggregateMetricDefs :: [OT.MetricDef]
  , aggregateDisplayDimensions :: [Text]
  , aggregateFilterValues :: [QI.Filter]
  , aggregateRowPredicateValue :: Maybe QI.Predicate
  , aggregateResultPredicateValue :: Maybe QI.Predicate
  , aggregateLimitValue :: Maybe Int
  , aggregateAssumptions :: [Text]
  , aggregateMatchScore :: Int
  , aggregateSubjectAffinityScore :: Int
  }

data GroundedFind = GroundedFind
  { findFactObject :: Object
  , findTargetObject :: Object
  , findDisplayDimensions :: [QI.FindDisplaySpec]
  , findOrderValues :: [QI.FindOrderSpec]
  , findPredicateTreeValue :: Maybe QI.Predicate
  , findFilterValues :: [QI.Filter]
  , findLimitValue :: Maybe Int
  , findAssumptions :: [Text]
  , findMatchScore :: Int
  }

data DraftTask
  = DraftRank
  | DraftTrend
  | DraftAggregate
  | DraftFind
  | DraftCompare
  | DraftObject
  | DraftUnknown Text
