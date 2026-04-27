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

data ResolvedLinkedFilter = ResolvedLinkedFilter
  { targetObjectName :: Text
  , filterPath :: DiscoveredPath
  , filterColumn :: Text
  , filterValue :: Text
  }
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
  , windowGames :: Int
  , seasonLabel :: Maybe Text
  , seasonType :: Maybe Text
  , queryLimit :: Maybe Int
  , linkedFiltersResolved :: [ResolvedLinkedFilter]
  , comparisonEntities :: [ResolvedEntity]
  , comparisonRequestedValue :: Bool
  , resolvedAssumptions :: [Text]
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
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
  , filterLocation :: Text
  , timeFilterKind :: Text
  , trendFilters :: [Filter]
  , timeGrain :: Text
  , linkedFiltersResolved :: [ResolvedLinkedFilter]
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
  , seasonLabel :: Maybe Text
  , seasonType :: Maybe Text
  , queryLimit :: Maybe Int
  , linkedFiltersResolved :: [ResolvedLinkedFilter]
  , resolvedAssumptions :: [Text]
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindDisplay = ResolvedFindDisplay
  { displayPath :: DiscoveredPath
  , displayColumn :: Text
  , displayLabel :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindPredicate = ResolvedFindPredicate
  { predicatePath :: DiscoveredPath
  , predicateColumn :: Text
  , predicateLabel :: Text
  , predicateOp :: Text
  , predicateValue :: FilterValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindQuery = ResolvedFindQuery
  { resolvedFindFactTableName :: Text
  , resolvedFindTargetTableName :: Text
  , resolvedFindTargetObjectName :: Text
  , resolvedFindTargetPath :: DiscoveredPath
  , resolvedFindDisplays :: [ResolvedFindDisplay]
  , resolvedFindPredicates :: [ResolvedFindPredicate]
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
