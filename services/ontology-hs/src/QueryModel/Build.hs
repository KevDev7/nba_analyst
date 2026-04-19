-- Purpose:
-- Build an ontology-grounded semantic request into the structured query form
-- that can be normalized into the typed IR.
--
-- Uses:
-- - QueryModel/Ground.hs outputs
-- - planner-derived supported shapes
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

import CapabilityDerivation (DerivedFamily, deriveCapabilitiesIO, families)
import Data.Aeson (FromJSON)
import qualified Data.Aeson as Aeson
import qualified Data.ByteString.Lazy as BL
import qualified Data.Map.Strict as Map
import Data.Maybe (fromMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import GHC.Generics (Generic)
import OntologyLayer.Types (Ontology)
import QueryModel.Ground
import QueryModel.Intent (extractQueryIntent)
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
  = SemanticMetricQuery SemanticBaseQuery [QI.EntityRef] (Maybe SemanticComparison)
  | SemanticObjectQuery SemanticBaseQuery Text
  deriving (Show, Eq, Generic)

data ComparisonAliasEntity = ComparisonAliasEntity
  { entity_id :: Int
  , entity_name :: Text
  }
  deriving (Show, Eq, Generic, FromJSON)

data ComparisonAliasMatch = ComparisonAliasMatch
  { status :: Text
  , entity :: Maybe ComparisonAliasEntity
  , matches :: Maybe [ComparisonAliasEntity]
  }
  deriving (Show, Eq, Generic, FromJSON)

data ComparisonAliasIndex = ComparisonAliasIndex
  { aliases :: Map.Map Text ComparisonAliasMatch
  }
  deriving (Show, Eq, Generic, FromJSON)

data CapabilityArtifact = CapabilityArtifact
  { comparison_entity_indexes :: Map.Map Text (Map.Map Text ComparisonAliasIndex)
  }
  deriving (Show, Eq, Generic, FromJSON)

type ComparisonIndexes = Map.Map Text (Map.Map Text ComparisonAliasIndex)

buildQueryFromQuestionIO :: Ontology -> Text -> IO (Either Text QI.Query)
buildQueryFromQuestionIO ontology questionText = do
  derivedCapabilityOutput <- deriveCapabilitiesIO ontology
  comparisonIndexes <- loadComparisonIndexesIO
  pure (buildQueryFromQuestion (families derivedCapabilityOutput) comparisonIndexes questionText)

buildQueryFromQuestion :: [DerivedFamily] -> ComparisonIndexes -> Text -> Either Text QI.Query
buildQueryFromQuestion derivedFamilies comparisonIndexes questionText = do
  let intent = extractQueryIntent questionText
  grounded <- groundIntent derivedFamilies intent
  semanticQuery <- buildSemanticQuery comparisonIndexes grounded
  pure (toIRQuery semanticQuery)

buildSemanticQuery :: ComparisonIndexes -> GroundedSemanticRequest -> Either Text SemanticQuery
buildSemanticQuery comparisonIndexes groundedRequest = do
  factObjectName <-
    maybe
      (Left "QueryModel.Build requires a grounded core fact object.")
      Right
      (candidateCoreFactObject groundedRequest)
  comparisonValue <- traverse (resolveGroundedComparison comparisonIndexes) (groundedComparison groundedRequest)
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
          , assumptions = QueryModel.Ground.unresolvedPieces groundedRequest
          }
  pure $
    case queryShape groundedRequest of
      GroundedMetricQuery ->
        SemanticMetricQuery baseQuery [] comparisonValue
      GroundedObjectQuery rowObjectName ->
        SemanticObjectQuery baseQuery rowObjectName

toIRQuery :: SemanticQuery -> QI.Query
toIRQuery semanticQuery =
  case semanticQuery of
    SemanticMetricQuery baseQuery entityFilters maybeComparison ->
      QI.MetricQuery
        QI.MetricQuerySpec
          { QI.sharedQuery = toIRBaseQuery baseQuery
          , QI.entityFilters = entityFilters
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
  toIRBackedExample Map.empty $
    GroundedSemanticRequest
      { queryShape = GroundedMetricQuery
      , selectedFamilyKey = "example_metric"
      , candidateCoreFactObject = Just "PlayerGame"
      , groundedMetrics = ["total_points"]
      , groundedDimensions = ["player_name"]
      , groundedEntityMentions = []
      , groundedTimeGrain = Nothing
      , groundedFilters = [GroundedFilter "last_n_games" (Just (QI.FilterInt 10))]
      , groundedLinkedFilters = []
      , groundedOrdering = Just (GroundedOrdering (Just "total_points") True)
      , groundedLimit = Just 10
      , groundedComparison = Nothing
      , unresolvedPieces = []
      }

exampleObjectSemanticQuery :: SemanticQuery
exampleObjectSemanticQuery =
  toIRBackedExample Map.empty $
    GroundedSemanticRequest
      { queryShape = GroundedObjectQuery "Player"
      , selectedFamilyKey = "example_object"
      , candidateCoreFactObject = Just "PlayerGame"
      , groundedMetrics = ["average_points"]
      , groundedDimensions = ["player_name"]
      , groundedEntityMentions = []
      , groundedTimeGrain = Nothing
      , groundedFilters = [GroundedFilter "last_n_games" (Just (QI.FilterInt 10))]
      , groundedLinkedFilters = []
      , groundedOrdering = Just (GroundedOrdering (Just "average_points") True)
      , groundedLimit = Nothing
      , groundedComparison = Nothing
      , unresolvedPieces = []
      }

toIRBackedExample :: ComparisonIndexes -> GroundedSemanticRequest -> SemanticQuery
toIRBackedExample comparisonIndexes groundedRequest =
  case buildSemanticQuery comparisonIndexes groundedRequest of
    Right semanticQuery -> semanticQuery
    Left err -> error ("QueryModel foundation example construction failed: " <> show err)

resolveGroundedComparison :: ComparisonIndexes -> GroundedComparison -> Either Text SemanticComparison
resolveGroundedComparison comparisonIndexes groundedComparisonValue = do
  resolvedEntities <- mapM (resolveComparisonEntity comparisonIndexes targetObjectName identityDimensionName) entityNamesValue
  pure
    SemanticComparison
      { semanticComparisonTargetObject = targetObjectName
      , semanticComparisonEntities = resolvedEntities
      }
  where
    targetObjectName =
      case groundedComparisonValue of
        GroundedComparison {QueryModel.Ground.targetObject = currentTargetObject} -> currentTargetObject
    identityDimensionName = identityDimension groundedComparisonValue
    entityNamesValue = entityNames groundedComparisonValue

resolveComparisonEntity :: ComparisonIndexes -> Text -> Text -> Text -> Either Text QI.EntityRef
resolveComparisonEntity comparisonIndexes targetObjectName dimensionName rawEntityName = do
  aliasIndex <-
    maybe
      (Left ("No comparison alias index is available for target object '" <> targetObjectName <> "'."))
      Right
      (Map.lookup targetObjectName comparisonIndexes >>= Map.lookup dimensionName)
  aliasMatch <-
    maybe
      (Left ("Could not resolve " <> targetObjectName <> " " <> dimensionName <> " value '" <> rawEntityName <> "' for comparison."))
      Right
      (Map.lookup (normalizeAlias rawEntityName) (aliases aliasIndex))
  case status aliasMatch of
    "resolved" ->
      case entity aliasMatch of
        Just resolvedEntity ->
          Right
            QI.EntityRef
              { QI.entityId = entity_id resolvedEntity
              , QI.entityName = entity_name resolvedEntity
              }
        Nothing -> Left ("Resolved comparison alias for '" <> rawEntityName <> "' did not include an entity payload.")
    "ambiguous" ->
      let candidateNames =
            T.intercalate
              ", "
              [ entity_name matchedEntity
              | matchedEntity <- fromMaybe [] (matches aliasMatch)
              ]
       in Left (targetObjectName <> " " <> dimensionName <> " value '" <> rawEntityName <> "' is ambiguous for comparison. Matches: " <> candidateNames <> ".")
    _ ->
      Left ("Could not resolve " <> targetObjectName <> " " <> dimensionName <> " value '" <> rawEntityName <> "' for comparison.")

loadComparisonIndexesIO :: IO ComparisonIndexes
loadComparisonIndexesIO = do
  artifactBytes <- BL.readFile "../../fixtures/interpreter/semantic-capabilities.json"
  case Aeson.eitherDecode artifactBytes of
    Left _ -> pure Map.empty
    Right capabilityArtifact -> pure (comparison_entity_indexes capabilityArtifact)

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
    (False, Just _) -> error "QueryModel.Build only normalizes descending ordering into the live IR."
    (_, Nothing) -> error "QueryModel.Build requires grounded ordering hints to name a metric."

toIRBaseQuery :: SemanticBaseQuery -> QI.BaseQuery
toIRBaseQuery semanticBase =
  QI.BaseQuery
    { QI.coreFactObject = coreFactObject semanticBase
    , QI.metrics = metrics semanticBase
    , QI.dimensions = dimensions semanticBase
    , QI.timeGrain = fmap QI.TimeGrainRef (timeGrain semanticBase)
    , QI.filters = map toIRFilter (QueryModel.Build.filters semanticBase)
    , QI.linkedFilters = map toIRLinkedFilter (QueryModel.Build.linkedFilters semanticBase)
    , QI.orders = map toIROrder (orders semanticBase)
    , QI.limit = limit semanticBase
    , QI.assumptions = QueryModel.Build.assumptions semanticBase
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

normalizeAlias :: Text -> Text
normalizeAlias =
  T.unwords . T.words . T.map normalizeChar . T.toLower
  where
    normalizeChar currentChar
      | T.any (== currentChar) "abcdefghijklmnopqrstuvwxyz0123456789" = currentChar
      | otherwise = ' '
