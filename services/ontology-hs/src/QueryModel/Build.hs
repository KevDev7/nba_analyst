-- Purpose:
-- Build an ontology-grounded semantic request into the structured query form
-- that can be normalized into the typed IR.
--
-- Uses:
-- - QueryModel/Ground.hs outputs
-- - query-shape rules for object queries vs metric queries
--
-- Produces:
-- - a DSL-like semantic query representation that is ready for normalization
--   into QueryModel/IR.hs
--
-- Next:
-- - QueryModel/IR.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.Build where

import Data.Text (Text)
import GHC.Generics (Generic)
import QueryModel.Ground
import QueryModel.Intent
import qualified QueryModel.IR as QI

data SemanticOrder
  = SemanticDesc Text
  deriving (Show, Eq, Generic)

data SemanticLinkedFilter = SemanticLinkedFilter
  { semanticTargetObject :: Text
  , semanticAttribute :: Text
  , semanticValue :: Text
  }
  deriving (Show, Eq, Generic)

data SemanticFilter = SemanticFilter
  { semanticFilterKind :: Text
  , semanticFilterValue :: Maybe QI.FilterValue
  }
  deriving (Show, Eq, Generic)

data SemanticBaseQuery = SemanticBaseQuery
  { coreFactObject :: Text
  , metrics :: [Text]
  , dimensions :: [Text]
  , timeGrain :: Maybe Text
  , filters :: [SemanticFilter]
  , linkedFilters :: [SemanticLinkedFilter]
  , orders :: [SemanticOrder]
  , limit :: Maybe Int
  , assumptions :: [Text]
  }
  deriving (Show, Eq, Generic)

data SemanticComparison = SemanticComparison
  { semanticComparisonTargetObject :: Text
  , semanticComparisonEntities :: [QI.EntityRef]
  }
  deriving (Show, Eq, Generic)

data SemanticQuery
  = SemanticMetricQuery SemanticBaseQuery (Maybe SemanticComparison)
  | SemanticObjectQuery SemanticBaseQuery Text
  deriving (Show, Eq, Generic)

buildSemanticQuery :: GroundedSemanticRequest -> Either Text SemanticQuery
buildSemanticQuery groundedRequest = do
  factObjectName <-
    maybe
      (Left "QueryModel.Build requires a grounded core fact object.")
      Right
      (candidateCoreFactObject groundedRequest)
  let baseQuery =
        SemanticBaseQuery
          { coreFactObject = factObjectName
          , metrics = groundedMetrics groundedRequest
          , dimensions = groundedDimensions groundedRequest
          , timeGrain = groundedTimeGrain groundedRequest
          , filters = map fromGroundedFilter (groundedFilters groundedRequest)
          , linkedFilters = map fromGroundedLinkedFilter (groundedLinkedFilters groundedRequest)
          , orders = maybe [] (\ordering -> [fromGroundedOrdering ordering]) (groundedOrdering groundedRequest)
          , limit = groundedLimit groundedRequest
          , assumptions = unresolvedPieces groundedRequest
          }
  pure $
    case queryShape groundedRequest of
      GroundedMetricQuery ->
        SemanticMetricQuery baseQuery (fmap fromGroundedComparison (groundedComparison groundedRequest))
      GroundedObjectQuery rowObjectName ->
        SemanticObjectQuery baseQuery rowObjectName

toIRQuery :: SemanticQuery -> QI.Query
toIRQuery semanticQuery =
  case semanticQuery of
    SemanticMetricQuery baseQuery maybeComparison ->
      QI.MetricQuery
        QI.MetricQuerySpec
          { QI.sharedQuery = toIRBaseQuery baseQuery
          , QI.entityFilters = []
          , QI.comparison = fmap toIRComparison maybeComparison
          }
    SemanticObjectQuery baseQuery rowObjectName ->
      QI.ObjectQuery
        QI.ObjectQuerySpec
          { QI.sharedQuery = toIRBaseQuery baseQuery
          , QI.rowObject = rowObjectName
          }

exampleMetricSemanticQuery :: SemanticQuery
exampleMetricSemanticQuery =
  toIRBackedExample $
    (groundedMetricRequest "PlayerGame")
      { groundedMetrics = ["total_points"]
      , groundedDimensions = ["player_name"]
      , groundedFilters = [GroundedFilter "last_n_games" (Just (QI.FilterInt 10))]
      , groundedOrdering = Just (GroundedOrdering (Just "total_points") True)
      , groundedLimit = Just 10
      }

exampleObjectSemanticQuery :: SemanticQuery
exampleObjectSemanticQuery =
  toIRBackedExample $
    (groundedObjectRequest "PlayerGame" "Player")
      { groundedMetrics = ["average_points"]
      , groundedDimensions = ["player_name"]
      , groundedFilters = [GroundedFilter "last_n_games" (Just (QI.FilterInt 10))]
      , groundedOrdering = Just (GroundedOrdering (Just "average_points") True)
      }

toIRBackedExample :: GroundedSemanticRequest -> SemanticQuery
toIRBackedExample groundedRequest =
  case buildSemanticQuery groundedRequest of
    Right semanticQuery -> semanticQuery
    Left err -> error ("QueryModel foundation example construction failed: " <> show err)

buildRecentPlayerRankingQuery :: [Text] -> Text -> Either Text QI.Query
buildRecentPlayerRankingQuery supportedMetrics questionText = do
  intent <-
    maybe
      (Left "QueryModel.Intent did not match the live recent player ranking QueryModel pattern.")
      Right
      (extractRecentPlayerRankingIntent questionText)
  grounded <- groundRecentPlayerRankingIntent supportedMetrics intent
  semanticQuery <- buildSemanticQuery grounded
  pure (toIRQuery semanticQuery)

fromGroundedFilter :: GroundedFilter -> SemanticFilter
fromGroundedFilter groundedFilter =
  let GroundedFilter {QueryModel.Ground.kind = kindValue, QueryModel.Ground.value = maybeValue} = groundedFilter
   in
  SemanticFilter
    { semanticFilterKind = kindValue
    , semanticFilterValue = maybeValue
    }

fromGroundedLinkedFilter :: GroundedLinkedFilter -> SemanticLinkedFilter
fromGroundedLinkedFilter groundedLinkedFilter =
  let GroundedLinkedFilter
        { QueryModel.Ground.targetObject = targetObjectValue
        , QueryModel.Ground.attribute = attributeValue
        , QueryModel.Ground.value = linkedValue
        } = groundedLinkedFilter
   in
  SemanticLinkedFilter
    { semanticTargetObject = targetObjectValue
    , semanticAttribute = attributeValue
    , semanticValue = linkedValue
    }

fromGroundedOrdering :: GroundedOrdering -> SemanticOrder
fromGroundedOrdering groundedOrderingValue =
  case (descending groundedOrderingValue, QueryModel.Ground.metric groundedOrderingValue) of
    (True, Just metricName) -> SemanticDesc metricName
    (False, Just _) -> error "QueryModel.Build foundation slice only normalizes descending ordering into the live IR."
    (_, Nothing) -> error "QueryModel.Build requires grounded ordering hints to name a metric."

fromGroundedComparison :: GroundedComparison -> SemanticComparison
fromGroundedComparison groundedComparisonValue =
  let GroundedComparison
        { QueryModel.Ground.targetObject = targetObjectValue
        , QueryModel.Ground.entities = groundedEntities
        } = groundedComparisonValue
   in
  SemanticComparison
    { semanticComparisonTargetObject = targetObjectValue
    , semanticComparisonEntities = groundedEntities
    }

toIRBaseQuery :: SemanticBaseQuery -> QI.BaseQuery
toIRBaseQuery semanticBase =
  QI.BaseQuery
    { QI.coreFactObject = coreFactObject semanticBase
    , QI.metrics = metrics semanticBase
    , QI.dimensions = dimensions semanticBase
    , QI.timeGrain = fmap QI.TimeGrainRef (timeGrain semanticBase)
    , QI.filters = map toIRFilter (filters semanticBase)
    , QI.linkedFilters = map toIRLinkedFilter (linkedFilters semanticBase)
    , QI.orders = map toIROrder (orders semanticBase)
    , QI.limit = limit semanticBase
    , QI.assumptions = assumptions semanticBase
    }

toIRFilter :: SemanticFilter -> QI.Filter
toIRFilter semanticFilter =
  QI.FilterRef
    { QI.kind = semanticFilterKind semanticFilter
    , QI.value = semanticFilterValue semanticFilter
    }

toIRLinkedFilter :: SemanticLinkedFilter -> QI.LinkedFilter
toIRLinkedFilter semanticLinkedFilter =
  QI.LinkedFilter
    { QI.targetObject = semanticTargetObject semanticLinkedFilter
    , QI.attribute = semanticAttribute semanticLinkedFilter
    , QI.value = semanticValue semanticLinkedFilter
    }

toIROrder :: SemanticOrder -> QI.Order
toIROrder semanticOrder =
  case semanticOrder of
    SemanticDesc metricName -> QI.Desc metricName

toIRComparison :: SemanticComparison -> QI.ComparisonIntent
toIRComparison semanticComparison =
  QI.CompareEntities
    (semanticComparisonTargetObject semanticComparison)
    (semanticComparisonEntities semanticComparison)
