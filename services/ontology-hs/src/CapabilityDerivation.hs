-- Purpose:
-- Derive interpreter capability families from actual planner behavior.
--
-- Uses:
-- - Query IR vocabulary
-- - ontology object inventory
-- - grounded planning validation, resolution, and compilation
--
-- Produces:
-- - supported capability families for the Python interpreter artifact
--
-- Next:
-- - app/Main.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE ScopedTypeVariables #-}

module CapabilityDerivation where

import Control.Exception (SomeException, evaluate, try)
import Data.Aeson (ToJSON, encode)
import qualified Data.ByteString.Lazy as BL
import Data.Char (isUpper, toLower)
import Data.List (nub, sort)
import qualified Data.Map.Strict as Map
import Data.Maybe (catMaybes, isJust)
import Data.Text (Text)
import qualified Data.Text as T
import GHC.Generics (Generic)
import GroundedPlanning.Compile (compileExecutionPlan)
import GroundedPlanning.Resolve (ResolvedQuery, resolveQuery)
import GroundedPlanning.Validation (validateQuery)
import OntologyLayer.Types (Ontology, objects)
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI

data LinkedFilterCapability = LinkedFilterCapability
  { target_object :: Text
  , attribute :: Text
  , required :: Bool
  }
  deriving (Show, Eq, Ord, Generic, ToJSON)

data DerivedComparison = DerivedComparison
  { enabled :: Bool
  , entity_type :: Maybe Text
  , max_entities :: Maybe Int
  }
  deriving (Show, Eq, Ord, Generic, ToJSON)

data DerivedFamily = DerivedFamily
  { family_key :: Text
  , query_kind :: Text
  , core_fact_object :: Text
  , row_object :: Maybe Text
  , metrics :: [Text]
  , dimensions :: [Text]
  , required_filter_kinds :: [Text]
  , time_grain :: Maybe Text
  , linked_filters :: [LinkedFilterCapability]
  , allow_limit :: Bool
  , require_order_by_metric :: Bool
  , comparison :: DerivedComparison
  }
  deriving (Show, Eq, Generic, ToJSON)

data DerivedCapabilityOutput = DerivedCapabilityOutput
  { families :: [DerivedFamily]
  }
  deriving (Show, Eq, Generic, ToJSON)

data FamilySignature = FamilySignature
  { sig_query_kind :: Text
  , sig_core_fact_object :: Text
  , sig_row_object :: Maybe Text
  , sig_dimensions :: [Text]
  , sig_required_filter_kinds :: [Text]
  , sig_time_grain :: Maybe Text
  , sig_linked_filters :: [LinkedFilterCapability]
  , sig_comparison :: DerivedComparison
  }
  deriving (Show, Eq, Ord)

data FamilyAccumulator = FamilyAccumulator
  { acc_metrics :: [Text]
  , acc_allow_limit :: Bool
  , acc_supports_order :: Bool
  , acc_supports_no_order :: Bool
  }
  deriving (Show, Eq)

deriveCapabilitiesIO :: Ontology -> IO DerivedCapabilityOutput
deriveCapabilitiesIO ontology =
  DerivedCapabilityOutput
    <$> (renderFamilies <$> supportedObservations ontology)

data SupportedObservation = SupportedObservation
  { supported_signature :: FamilySignature
  , supported_metric :: Text
  , supported_limit :: Bool
  , supported_order_present :: Bool
  }
  deriving (Show, Eq)

supportedObservations :: Ontology -> IO [SupportedObservation]
supportedObservations ontology =
  catMaybes
    <$> mapM
      ( \queryValue -> do
          supported <- queryIsSupported ontology queryValue
          pure $
            if supported
              then Just (toObservation queryValue)
              else Nothing
      )
      (enumerateCandidateQueries ontology)

enumerateCandidateQueries :: Ontology -> [QI.Query]
enumerateCandidateQueries ontology =
  enumerateMetricQueries ontology ++ enumerateObjectQueries ontology

enumerateMetricQueries :: Ontology -> [QI.Query]
enumerateMetricQueries ontology =
  [ QI.MetricQuery
      QI.MetricQuerySpec
        { QI.sharedQuery =
            QI.BaseQuery
              { QI.coreFactObject = factObjectName
              , QI.metrics = [metricValue]
              , QI.dimensions = dimensionValues
              , QI.timeGrain = timeGrainValue
              , QI.filters = filterValues
              , QI.linkedFilters = linkedFilterValues
              , QI.orders = orderValues
              , QI.limit = limitValue
              , QI.assumptions = []
              }
        , QI.entityFilters = entityFilterValues
        , QI.comparison = comparisonValue
        }
  | factObjectName <- ontologyObjectNames ontology
  , metricValue <- allMetrics
  , dimensionValues <- metricDimensionCandidates
  , (filterValues, timeGrainValue) <- filterBundleCandidates
  , linkedFilterValues <- linkedFilterCandidates
  , (entityFilterValues, comparisonValue) <- comparisonCandidates
  , orderValues <- metricOrderCandidates metricValue comparisonValue
  , limitValue <- metricLimitCandidates comparisonValue
  ]

enumerateObjectQueries :: Ontology -> [QI.Query]
enumerateObjectQueries ontology =
  [ QI.ObjectQuery
      QI.ObjectQuerySpec
        { QI.sharedQuery =
            QI.BaseQuery
              { QI.coreFactObject = factObjectName
              , QI.metrics = [metricValue]
              , QI.dimensions = dimensionValues
              , QI.timeGrain = Nothing
              , QI.filters = filterValues
              , QI.linkedFilters = linkedFilterValues
              , QI.orders = orderValues
              , QI.limit = limitValue
              , QI.assumptions = []
              }
        , QI.rowObject = rowObjectName
        }
  | factObjectName <- ontologyObjectNames ontology
  , rowObjectName <- ontologyObjectNames ontology
  , metricValue <- allMetrics
  , dimensionValues <- objectDimensionCandidates
  , (filterValues, _) <- filterBundleCandidates
  , linkedFilterValues <- linkedFilterCandidates
  , orderValues <- objectOrderCandidates metricValue
  , limitValue <- objectLimitCandidates
  ]

ontologyObjectNames :: Ontology -> [Text]
ontologyObjectNames ontology =
  [ currentName
  | OT.Object {OT.name = currentName} <- objects ontology
  ]

allMetrics :: [QI.MetricName]
allMetrics =
  [ QI.TotalPoints
  , QI.AveragePoints
  , QI.GamesPlayed
  , QI.PointsPer36
  , QI.Wins
  , QI.Losses
  , QI.WinPercentage
  ]

metricDimensionCandidates :: [[QI.DimensionName]]
metricDimensionCandidates =
  [ []
  , [QI.PlayerName]
  , [QI.TeamName]
  , [QI.DisplayName]
  , [QI.Team]
  , [QI.PrimaryPosition]
  ]

objectDimensionCandidates :: [[QI.DimensionName]]
objectDimensionCandidates =
  [ [QI.PlayerName]
  , [QI.TeamName]
  , [QI.DisplayName]
  , [QI.Team]
  , [QI.PrimaryPosition]
  ]

filterBundleCandidates :: [([QI.Filter], Maybe QI.TimeGrain)]
filterBundleCandidates =
  [ ([QI.LastNGames 10], Nothing)
  , ([QI.PastYear], Just QI.Month)
  , ([QI.ExactSeason "2025-26", QI.SeasonTypeFilter "regular_season"], Nothing)
  ]

linkedFilterCandidates :: [[QI.LinkedFilter]]
linkedFilterCandidates =
  -- Temporary derivation seed set. Slice 12 only proves the first linked team
  -- filter family here; grow or derive values more generally instead of
  -- preserving this single concrete example long term.
  [ []
  , [QI.LinkedFilter "Team" "team_name" "Lakers"]
  ]

comparisonCandidates :: [([QI.PlayerRef], Maybe QI.ComparisonIntent)]
comparisonCandidates =
  -- Temporary derivation seed set. Slice 13 proves generalized player refs, but
  -- capability derivation still probes one structural two-player comparison
  -- shape rather than a fully generative comparison space.
  [ ([], Nothing)
  ,
      ( [ QI.PlayerRef 1 "Comparison Player A"
        , QI.PlayerRef 2 "Comparison Player B"
        ]
      , Just
          ( QI.CompareEntities
              [ QI.PlayerRef 1 "Comparison Player A"
              , QI.PlayerRef 2 "Comparison Player B"
              ]
          )
      )
  ]

metricOrderCandidates :: QI.MetricName -> Maybe QI.ComparisonIntent -> [[QI.Order]]
metricOrderCandidates metricValue maybeComparison =
  case maybeComparison of
    Just _ -> [[]]
    Nothing -> [[], [QI.Desc metricValue]]

objectOrderCandidates :: QI.MetricName -> [[QI.Order]]
objectOrderCandidates metricValue =
  [ []
  , [QI.Desc metricValue]
  ]

metricLimitCandidates :: Maybe QI.ComparisonIntent -> [Maybe Int]
metricLimitCandidates maybeComparison =
  -- Temporary derivation seed set. We only probe the limit shapes the product
  -- currently cares about rather than exhaustively modeling all legal limits.
  case maybeComparison of
    Just _ -> [Nothing]
    Nothing -> [Nothing, Just 5]

objectLimitCandidates :: [Maybe Int]
-- Temporary derivation seed set paired with the current retained-bank proof.
objectLimitCandidates = [Nothing, Just 5]

queryIsSupported :: Ontology -> QI.Query -> IO Bool
queryIsSupported ontology queryValue =
  case validateQuery ontology queryValue of
    Left _ -> pure False
    Right () ->
      case resolveQuery ontology queryValue of
        Left _ -> pure False
        Right resolvedQuery -> compileQuerySafely resolvedQuery

compileQuerySafely :: ResolvedQuery -> IO Bool
compileQuerySafely resolvedQuery = do
  compiledResult <- try $
    evaluate $
      BL.length $
        encode $
          compileExecutionPlan resolvedQuery
  case compiledResult of
    Left (_ :: SomeException) -> pure False
    Right encodedLength -> pure (encodedLength > 0)

toObservation :: QI.Query -> SupportedObservation
toObservation queryValue =
  case queryValue of
    QI.MetricQuery spec@QI.MetricQuerySpec {QI.sharedQuery = base} ->
      SupportedObservation
        { supported_signature = familySignatureFromMetric spec
        , supported_metric = metricTextFromList (QI.metrics base)
        , supported_limit = isJust (QI.limit base)
        , supported_order_present = not (null (QI.orders base))
        }
    QI.ObjectQuery spec@QI.ObjectQuerySpec {QI.sharedQuery = base} ->
      SupportedObservation
        { supported_signature = familySignatureFromObject spec
        , supported_metric = metricTextFromList (QI.metrics base)
        , supported_limit = isJust (QI.limit base)
        , supported_order_present = not (null (QI.orders base))
        }

familySignatureFromMetric :: QI.MetricQuerySpec -> FamilySignature
familySignatureFromMetric spec@QI.MetricQuerySpec {QI.sharedQuery = base} =
  FamilySignature
    { sig_query_kind = "metric_query"
    , sig_core_fact_object = QI.coreFactObject base
    , sig_row_object = Nothing
    , sig_dimensions = map dimensionText (QI.dimensions base)
    , sig_required_filter_kinds = sort (map filterKindText (QI.filters base))
    , sig_time_grain = fmap timeGrainText (QI.timeGrain base)
    , sig_linked_filters = linkedFilterCapabilities (QI.linkedFilters base)
    , sig_comparison =
        case QI.comparison spec of
          Just (QI.CompareEntities entities) ->
            DerivedComparison True (Just "player") (Just (length entities))
          Nothing -> DerivedComparison False Nothing Nothing
    }

familySignatureFromObject :: QI.ObjectQuerySpec -> FamilySignature
familySignatureFromObject spec@QI.ObjectQuerySpec {QI.sharedQuery = base} =
  FamilySignature
    { sig_query_kind = "object_query"
    , sig_core_fact_object = QI.coreFactObject base
    , sig_row_object = Just (QI.rowObject spec)
    , sig_dimensions = map dimensionText (QI.dimensions base)
    , sig_required_filter_kinds = sort (map filterKindText (QI.filters base))
    , sig_time_grain = fmap timeGrainText (QI.timeGrain base)
    , sig_linked_filters = linkedFilterCapabilities (QI.linkedFilters base)
    , sig_comparison = DerivedComparison False Nothing Nothing
    }

linkedFilterCapabilities :: [QI.LinkedFilter] -> [LinkedFilterCapability]
linkedFilterCapabilities =
  map
    ( \linkedFilterValue ->
        LinkedFilterCapability
          { target_object = QI.targetObject linkedFilterValue
          , attribute = QI.attribute linkedFilterValue
          , required = True
          }
    )

renderFamilies :: [SupportedObservation] -> [DerivedFamily]
renderFamilies observations =
  map renderFamily (Map.toAscList grouped)
  where
    grouped :: Map.Map FamilySignature FamilyAccumulator
    grouped =
      foldl' accumulateObservation Map.empty observations

    accumulateObservation :: Map.Map FamilySignature FamilyAccumulator -> SupportedObservation -> Map.Map FamilySignature FamilyAccumulator
    accumulateObservation currentMap observation =
      Map.insertWith mergeAccumulator (supported_signature observation) newAccumulator currentMap
      where
        newAccumulator =
          FamilyAccumulator
            { acc_metrics = [supported_metric observation]
            , acc_allow_limit = supported_limit observation
            , acc_supports_order = supported_order_present observation
            , acc_supports_no_order = not (supported_order_present observation)
            }

    mergeAccumulator :: FamilyAccumulator -> FamilyAccumulator -> FamilyAccumulator
    mergeAccumulator newValue oldValue =
      FamilyAccumulator
        { acc_metrics = sort (nub (acc_metrics newValue ++ acc_metrics oldValue))
        , acc_allow_limit = acc_allow_limit newValue || acc_allow_limit oldValue
        , acc_supports_order = acc_supports_order newValue || acc_supports_order oldValue
        , acc_supports_no_order = acc_supports_no_order newValue || acc_supports_no_order oldValue
        }

    renderFamily :: (FamilySignature, FamilyAccumulator) -> DerivedFamily
    renderFamily (signatureValue, accumulatorValue) =
      DerivedFamily
        { family_key = familyKey signatureValue
        , query_kind = sig_query_kind signatureValue
        , core_fact_object = sig_core_fact_object signatureValue
        , row_object = sig_row_object signatureValue
        , metrics = acc_metrics accumulatorValue
        , dimensions = sig_dimensions signatureValue
        , required_filter_kinds = sig_required_filter_kinds signatureValue
        , time_grain = sig_time_grain signatureValue
        , linked_filters = sig_linked_filters signatureValue
        , allow_limit = acc_allow_limit accumulatorValue
        , require_order_by_metric =
            acc_supports_order accumulatorValue && not (acc_supports_no_order accumulatorValue)
        , comparison = sig_comparison signatureValue
        }

familyKey :: FamilySignature -> Text
familyKey signatureValue =
  -- Temporary naming helper for interpreter-facing summaries. These keys are a
  -- convenience surface, not a semantic source of truth.
  T.intercalate
    "_"
    ( filter
        (not . T.null)
        [ snakeCase (sig_core_fact_object signatureValue)
        , filterBundleKey (sig_required_filter_kinds signatureValue) (sig_time_grain signatureValue)
        , queryKindKey (sig_query_kind signatureValue)
        , rowObjectKey (sig_row_object signatureValue)
        , dimensionKeyFragment (sig_dimensions signatureValue)
        , linkedFilterKey (sig_linked_filters signatureValue)
        , comparisonKey (sig_comparison signatureValue)
        ]
    )

filterBundleKey :: [Text] -> Maybe Text -> Text
filterBundleKey filterKinds maybeTimeGrain =
  case (sort filterKinds, maybeTimeGrain) of
    (["last_n_games"], _) -> "recent"
    (["past_year"], Just "month") -> "monthly"
    (["exact_season", "season_type"], _) -> "season"
    _ -> T.intercalate "_" filterKinds

queryKindKey :: Text -> Text
queryKindKey queryKindValue =
  case queryKindValue of
    "metric_query" -> "metric"
    "object_query" -> "object"
    _ -> queryKindValue

rowObjectKey :: Maybe Text -> Text
rowObjectKey maybeRowObject =
  case maybeRowObject of
    Just rowObjectValue -> snakeCase rowObjectValue
    Nothing -> ""

dimensionKeyFragment :: [Text] -> Text
dimensionKeyFragment dimensionValues =
  case dimensionValues of
    [] -> ""
    [dimensionValue] ->
      case dimensionValue of
        "player_name" -> ""
        "team_name" -> "by_team"
        otherValue -> otherValue
    otherValues -> T.intercalate "_" otherValues

linkedFilterKey :: [LinkedFilterCapability] -> Text
linkedFilterKey linkedFilterValues =
  case linkedFilterValues of
    [] -> ""
    _ -> "team_filter"

comparisonKey :: DerivedComparison -> Text
comparisonKey comparisonValue =
  if enabled comparisonValue
    then "comparison"
    else ""

metricTextFromList :: [QI.MetricName] -> Text
metricTextFromList metricValues =
  case metricValues of
    [metricValue] -> metricText metricValue
    _ -> error "Capability derivation expected exactly one selected metric."

metricText :: QI.MetricName -> Text
metricText metricValue =
  case metricValue of
    QI.TotalPoints -> "total_points"
    QI.AveragePoints -> "average_points"
    QI.GamesPlayed -> "games_played"
    QI.PointsPer36 -> "points_per_36"
    QI.Wins -> "wins"
    QI.Losses -> "losses"
    QI.WinPercentage -> "win_percentage"

dimensionText :: QI.DimensionName -> Text
dimensionText dimensionValue =
  case dimensionValue of
    QI.PlayerName -> "player_name"
    QI.TeamName -> "team_name"
    QI.DisplayName -> "display_name"
    QI.Team -> "team"
    QI.PrimaryPosition -> "primary_position"

timeGrainText :: QI.TimeGrain -> Text
timeGrainText timeGrainValue =
  case timeGrainValue of
    QI.Month -> "month"

filterKindText :: QI.Filter -> Text
filterKindText filterValue =
  case filterValue of
    QI.LastNGames _ -> "last_n_games"
    QI.PastYear -> "past_year"
    QI.ExactSeason _ -> "exact_season"
    QI.SeasonTypeFilter _ -> "season_type"

snakeCase :: Text -> Text
snakeCase textValue =
  T.pack (dropWhile (== '_') (go True (T.unpack textValue)))
  where
    go :: Bool -> String -> String
    go _ [] = []
    go isFirstCharacter (currentChar : remainingChars)
      | isUpper currentChar =
          let prefix = if isFirstCharacter then [] else "_"
           in prefix ++ [toLower currentChar] ++ go False remainingChars
      | otherwise = currentChar : go False remainingChars
