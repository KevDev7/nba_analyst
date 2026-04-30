{-# LANGUAGE DuplicateRecordFields #-}

module QueryModel.SemanticConstruction.Types
  ( GroundedAggregate(..)
  , GroundedComparison(..)
  , GroundedFind(..)
  , GroundedRanking(..)
  , GroundedTrend(..)
  , SemanticGroupingDimension(..)
  , TimeScope(..)
  ) where

import Data.Text (Text)
import OntologyLayer.Types (Object)
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI

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
