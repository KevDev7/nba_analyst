{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Types where

import Data.Aeson (FromJSON, ToJSON (toJSON), object, (.=))
import Data.Text (Text)
import GHC.Generics (Generic)
import OntologyLayer.Graph (DiscoveredPath)
import QueryModel.IR

data ResolvedEntity = ResolvedEntity
  { entityIdValue :: Int
  , entityName :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ColumnRef = ColumnRef
  { tableRole :: Text
  , columnName :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedMetricFormula = ResolvedMetricFormula
  { metricKey :: Text
  , aggregationKind :: Text
  , sourceAttributes :: [Text]
  , expressionText :: Text
  , executableInSlice :: Bool
  , resultColumn :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedDisplayMetadata = ResolvedDisplayMetadata
  { metadataKey :: Text
  , metadataLabel :: Text
  , metadataColumnType :: Text
  , metadataSource :: Maybe ColumnRef
  , metadataAggregation :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedGroupingDimension = ResolvedGroupingDimension
  { groupingKey :: Text
  , groupingLabel :: Text
  , groupingPath :: DiscoveredPath
  , groupingSource :: ColumnRef
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedRowPredicateLeaf = ResolvedRowPredicateLeaf
  { rowPredicateTargetObjectName :: Text
  , rowPredicatePath :: DiscoveredPath
  , rowPredicateColumn :: Text
  , rowPredicateLabel :: Text
  , rowPredicateOperator :: PredicateOperator
  , rowPredicateValue :: PredicateValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedRowPredicateTree
  = ResolvedRowPredicateLeafNode ResolvedRowPredicateLeaf
  | ResolvedRowPredicateAnd [ResolvedRowPredicateTree]
  | ResolvedRowPredicateOr [ResolvedRowPredicateTree]
  | ResolvedRowPredicateNot ResolvedRowPredicateTree
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedResultPredicateLeaf = ResolvedResultPredicateLeaf
  { resultPredicateKey :: Text
  , resultPredicateLabel :: Text
  , resultPredicateColumn :: Maybe Text
  , resultPredicateAggregation :: Text
  , resultPredicateOperator :: PredicateOperator
  , resultPredicateValue :: PredicateValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedResultPredicateTree
  = ResolvedResultPredicateLeafNode ResolvedResultPredicateLeaf
  | ResolvedResultPredicateAnd [ResolvedResultPredicateTree]
  | ResolvedResultPredicateOr [ResolvedResultPredicateTree]
  | ResolvedResultPredicateNot ResolvedResultPredicateTree
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedMetricQuery = ResolvedMetricQuery
  { factTableName :: Text
  , rowTableName :: Text
  , rowObjectName :: Text
  , metricResultShape :: Text
  , metricOrderDirection :: Text
  , rowPath :: DiscoveredPath
  , contextPath :: Maybe DiscoveredPath
  , partitionKey :: ColumnRef
  , entityId :: ColumnRef
  , displayName :: ColumnRef
  , contextValue :: Maybe ColumnRef
  , gameDate :: ColumnRef
  , metricSource :: ColumnRef
  , metricTimeGrain :: Maybe Text
  , metricTimeBucketExpression :: Maybe Text
  , windowGames :: Int
  , timeFilterKind :: Text
  , timeFilters :: [Filter]
  , seasonLabel :: Maybe Text
  , seasonType :: Maybe Text
  , queryLimit :: Maybe Int
  , rowPredicateResolved :: Maybe ResolvedRowPredicateTree
  , resultPredicateResolved :: Maybe ResolvedResultPredicateTree
  , comparisonEntities :: [ResolvedEntity]
  , comparisonRequestedValue :: Bool
  , resolvedAssumptions :: [Text]
  , metricFormula :: ResolvedMetricFormula
  , displayMetricFormulas :: [ResolvedMetricFormula]
  , filterLocation :: Text
  , groupingDimensions :: [ResolvedGroupingDimension]
  , displayMetadata :: [ResolvedDisplayMetadata]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedTrendQuery = ResolvedTrendQuery
  { factTableName :: Text
  , seriesTableName :: Maybe Text
  , seriesObjectName :: Maybe Text
  , seriesPath :: Maybe DiscoveredPath
  , seriesName :: Maybe ColumnRef
  , timeBucketName :: Text
  , timeBucketExpression :: Text
  , metricSource :: ColumnRef
  , metricFormula :: ResolvedMetricFormula
  , trendDisplayMetricFormulas :: [ResolvedMetricFormula]
  , filterLocation :: Text
  , timeFilterKind :: Text
  , trendFilters :: [Filter]
  , timeGrain :: Text
  , trendSeasonLabel :: Maybe Text
  , trendSeasonType :: Maybe Text
  , trendRowPredicateResolved :: Maybe ResolvedRowPredicateTree
  , trendResultPredicateResolved :: Maybe ResolvedResultPredicateTree
  , trendGroupingDimensions :: [ResolvedGroupingDimension]
  , resolvedAssumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedObjectQuery = ResolvedObjectQuery
  { rowTableName :: Text
  , factTableName :: Text
  , rowObjectName :: Text
  , objectOrderDirection :: Text
  , rowPath :: DiscoveredPath
  , contextPath :: Maybe DiscoveredPath
  , partitionKey :: ColumnRef
  , entityId :: ColumnRef
  , displayName :: ColumnRef
  , contextValue :: Maybe ColumnRef
  , gameDate :: ColumnRef
  , metricSource :: ColumnRef
  , windowGames :: Int
  , timeFilterKind :: Text
  , timeFilters :: [Filter]
  , seasonLabel :: Maybe Text
  , seasonType :: Maybe Text
  , queryLimit :: Maybe Int
  , objectRowPredicateResolved :: Maybe ResolvedRowPredicateTree
  , objectResultPredicateResolved :: Maybe ResolvedResultPredicateTree
  , resolvedAssumptions :: [Text]
  , metricFormula :: ResolvedMetricFormula
  , displayMetricFormulas :: [ResolvedMetricFormula]
  , filterLocation :: Text
  , displayMetadata :: [ResolvedDisplayMetadata]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindDisplay = ResolvedFindDisplay
  { displayPath :: DiscoveredPath
  , displayColumn :: Text
  , displayLabel :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindOrder = ResolvedFindOrder
  { orderPath :: DiscoveredPath
  , orderColumn :: Text
  , orderLabel :: Text
  , orderDirection :: FindOrderDirection
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindPredicateLeaf = ResolvedFindPredicateLeaf
  { treePredicateTargetObjectName :: Text
  , treePredicatePath :: DiscoveredPath
  , treePredicateColumn :: Text
  , treePredicateLabel :: Text
  , treePredicateLinkRole :: Maybe Text
  , treePredicateOperator :: PredicateOperator
  , treePredicateValue :: PredicateValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindPredicateTree
  = ResolvedFindPredicateLeafNode ResolvedFindPredicateLeaf
  | ResolvedFindPredicateAnd [ResolvedFindPredicateTree]
  | ResolvedFindPredicateOr [ResolvedFindPredicateTree]
  | ResolvedFindPredicateNot ResolvedFindPredicateTree
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindQuery = ResolvedFindQuery
  { resolvedFindFactTableName :: Text
  , resolvedFindTargetTableName :: Text
  , resolvedFindTargetObjectName :: Text
  , resolvedFindTargetPath :: DiscoveredPath
  , resolvedFindDisplays :: [ResolvedFindDisplay]
  , resolvedFindOrders :: [ResolvedFindOrder]
  , resolvedFindPredicateTree :: Maybe ResolvedFindPredicateTree
  , resolvedFindFilters :: [Filter]
  , resolvedFindLimit :: Maybe Int
  , resolvedFindAssumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedQuery
  = ResolvedMetric ResolvedMetricQuery
  | ResolvedTrend ResolvedTrendQuery
  | ResolvedObject ResolvedObjectQuery
  | ResolvedFind ResolvedFindQuery
  deriving (Show, Eq, Generic)

instance ToJSON ResolvedQuery where
  toJSON (ResolvedMetric resolved) =
    object ["kind" .= ("metric_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedTrend resolved) =
    object ["kind" .= ("metric_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedObject resolved) =
    object ["kind" .= ("object_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedFind resolved) =
    object ["kind" .= ("find_query" :: Text), "resolved" .= resolved]

data ContextSelection = ContextSelection
  { selectedContextPath :: Maybe DiscoveredPath
  , selectedContextColumn :: Maybe ColumnRef
  }
