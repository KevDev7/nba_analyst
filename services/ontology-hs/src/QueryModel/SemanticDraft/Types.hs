{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Types
  ( AggregateDimension(..)
  , DraftFilter(..)
  , DraftFreeformObject(..)
  , DraftTask(..)
  , DraftTimeWindow(..)
  , GroundedAggregate(..)
  , GroundedComparison(..)
  , GroundedFind(..)
  , GroundedRanking(..)
  , GroundedTrend(..)
  , RankingFilterBundle(..)
  , SemanticDraft(..)
  ) where

import Data.Aeson (FromJSON (parseJSON), withObject, (.:), (.:?), (.!=))
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
  , timeWindow :: DraftTimeWindow
  , grain :: Maybe Text
  , order :: [DraftFreeformObject]
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
  , displayDimension :: Text
  , filterValues :: [QI.Filter]
  , limitValue :: Maybe Int
  , assumptionValues :: [Text]
  , matchScore :: Int
  , subjectAffinityScore :: Int
  }

data RankingFilterBundle
  = RecentRanking Int
  | SeasonRanking Text Text
  deriving (Show, Eq)

data GroundedTrend = GroundedTrend
  -- A trend draft after ontology grounding.
  -- It identifies the fact surface, metric, optional series dimension, grain,
  -- and filters needed to build a typed time-series Query IR.
  { trendFactObject :: Object
  , trendMetricDef :: OT.MetricDef
  , trendDisplayDimension :: Maybe Text
  , trendGrainValue :: Text
  , trendFilterValues :: [QI.Filter]
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
  , comparisonDisplayDimension :: Text
  , comparisonFilterValues :: [QI.Filter]
  , comparisonEntitiesValue :: [QI.EntityRef]
  , comparisonAssumptions :: [Text]
  , comparisonMatchScore :: Int
  , comparisonSubjectAffinityScore :: Int
  }

data AggregateDimension = AggregateDimension
  { aggregateDimensionObject :: Object
  , aggregateDimensionName :: Text
  }

data GroundedAggregate = GroundedAggregate
  -- An aggregate draft after ontology grounding.
  -- It identifies the fact surface, metric, and public grouping dimension
  -- needed to build grouped metric-query IR without adding a ranking shape.
  { aggregateFactObject :: Object
  , aggregateGroupObject :: Object
  , aggregateMetricDef :: OT.MetricDef
  , aggregateDisplayDimension :: Text
  , aggregateFilterValues :: [QI.Filter]
  , aggregateLimitValue :: Maybe Int
  , aggregateAssumptions :: [Text]
  , aggregateMatchScore :: Int
  , aggregateSubjectAffinityScore :: Int
  }

data GroundedFind = GroundedFind
  { findFactObject :: Object
  , findTargetObject :: Object
  , findDisplayDimensions :: [Text]
  , findPredicateValues :: [QI.FindPredicate]
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
  | DraftUnknown Text
