-- Purpose:
-- Ground loose semantic intent onto actual ontology concepts, paths, and
-- business definitions.
--
-- Uses:
-- - QueryModel/Intent.hs outputs
-- - OntologyLayer types and graph traversal
-- - lexical matching, alias matching, and later embeddings / hybrid matching
--
-- Produces:
-- - an ontology-grounded semantic request that is specific enough to build into
--   a DSL-like query form
--
-- Next:
-- - QueryModel/Build.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}

module QueryModel.Ground where

import Data.Text (Text)
import GHC.Generics (Generic)
import qualified QueryModel.IR as QI

data GroundedQueryShape
  = GroundedMetricQuery
  | GroundedObjectQuery Text
  deriving (Show, Eq, Generic)

data GroundedOrdering = GroundedOrdering
  { metric :: Maybe Text
  , descending :: Bool
  }
  deriving (Show, Eq, Generic)

data GroundedFilter = GroundedFilter
  { kind :: Text
  , value :: Maybe QI.FilterValue
  }
  deriving (Show, Eq, Generic)

data GroundedLinkedFilter = GroundedLinkedFilter
  { targetObject :: Text
  , attribute :: Text
  , value :: Text
  }
  deriving (Show, Eq, Generic)

data GroundedComparison = GroundedComparison
  { targetObject :: Text
  , identityDimension :: Text
  , entities :: [QI.EntityRef]
  }
  deriving (Show, Eq, Generic)

data GroundedSemanticRequest = GroundedSemanticRequest
  { queryShape :: GroundedQueryShape
  , candidateCoreFactObject :: Maybe Text
  , groundedMetrics :: [Text]
  , groundedDimensions :: [Text]
  , groundedTimeGrain :: Maybe Text
  , groundedFilters :: [GroundedFilter]
  , groundedLinkedFilters :: [GroundedLinkedFilter]
  , groundedOrdering :: Maybe GroundedOrdering
  , groundedLimit :: Maybe Int
  , groundedComparison :: Maybe GroundedComparison
  , unresolvedPieces :: [Text]
  }
  deriving (Show, Eq, Generic)

groundedMetricRequest :: Text -> GroundedSemanticRequest
groundedMetricRequest factObjectName =
  GroundedSemanticRequest
    { queryShape = GroundedMetricQuery
    , candidateCoreFactObject = Just factObjectName
    , groundedMetrics = []
    , groundedDimensions = []
    , groundedTimeGrain = Nothing
    , groundedFilters = []
    , groundedLinkedFilters = []
    , groundedOrdering = Nothing
    , groundedLimit = Nothing
    , groundedComparison = Nothing
    , unresolvedPieces = []
    }

groundedObjectRequest :: Text -> Text -> GroundedSemanticRequest
groundedObjectRequest factObjectName rowObjectName =
  (groundedMetricRequest factObjectName)
    { queryShape = GroundedObjectQuery rowObjectName
    }
