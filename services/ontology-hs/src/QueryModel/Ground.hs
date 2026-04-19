-- Purpose:
-- Ground loose semantic intent onto actual ontology concepts, paths, and
-- planner-supported shapes.
--
-- Uses:
-- - QueryModel/Intent.hs outputs
-- - planner-derived capability families
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
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.Ground where

import CapabilityDerivation (DerivedComparison (DerivedComparison), DerivedFamily (..), LinkedFilterCapability (..))
import Data.List (nub, sort, sortOn)
import Data.Text (Text)
import qualified Data.Text as T
import GHC.Generics (Generic)
import QueryModel.Intent
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
  , entityNames :: [Text]
  }
  deriving (Show, Eq, Generic)

data GroundedSemanticRequest = GroundedSemanticRequest
  { queryShape :: GroundedQueryShape
  , selectedFamilyKey :: Text
  , candidateCoreFactObject :: Maybe Text
  , groundedMetrics :: [Text]
  , groundedDimensions :: [Text]
  , groundedEntityMentions :: [Text]
  , groundedTimeGrain :: Maybe Text
  , groundedFilters :: [GroundedFilter]
  , groundedLinkedFilters :: [GroundedLinkedFilter]
  , groundedOrdering :: Maybe GroundedOrdering
  , groundedLimit :: Maybe Int
  , groundedComparison :: Maybe GroundedComparison
  , unresolvedPieces :: [Text]
  }
  deriving (Show, Eq, Generic)

groundIntent :: [DerivedFamily] -> QueryIntent -> Either Text GroundedSemanticRequest
groundIntent derivedFamilies queryIntent = do
  metricName <- resolveSelectedMetric queryIntent
  targetFilterKinds <- resolveTargetFilterKinds queryIntent
  let shapeKind = inferGroundShape queryIntent
      desiredRowObject = resolveDesiredRowObject queryIntent shapeKind
      desiredDimensions = resolveDesiredDimensions queryIntent shapeKind desiredRowObject
      desiredLinkedFilters = linkedFilters queryIntent
      compatibleFamilies =
        filter
          (familyMatchesIntent shapeKind metricName targetFilterKinds desiredRowObject desiredDimensions desiredLinkedFilters queryIntent)
          derivedFamilies
  case compatibleFamilies of
    [] ->
      if not (null (singleEntityMentions queryIntent))
        then Left "No planner-supported shape accepts non-comparison single-entity filters yet."
        else Left "No planner-supported grounded shape matched the extracted semantic intent."
    _ -> do
      selectedFamily <-
        case rankCandidateFamilies shapeKind targetFilterKinds desiredRowObject desiredLinkedFilters compatibleFamilies of
          rankedFamily : _ -> Right rankedFamily
          [] -> Left "No planner-supported grounded shape matched the extracted semantic intent."
      groundedComparisonValue <- groundComparisonIfNeeded queryIntent selectedFamily desiredDimensions
      pure
        GroundedSemanticRequest
          { queryShape = groundedShapeFromFamily selectedFamily
          , selectedFamilyKey = family_key selectedFamily
          , candidateCoreFactObject = Just (core_fact_object selectedFamily)
          , groundedMetrics = [metricName]
          , groundedDimensions = desiredDimensions
          , groundedEntityMentions = singleEntityMentions queryIntent
          , groundedTimeGrain = time_grain selectedFamily
          , groundedFilters = map intentFilterToGroundedFilter (filters queryIntent)
          , groundedLinkedFilters = map linkedFilterToGroundedFilter desiredLinkedFilters
          , groundedOrdering = buildGroundedOrdering shapeKind metricName
          , groundedLimit = limitHint queryIntent
          , groundedComparison = groundedComparisonValue
          , unresolvedPieces = assumptions queryIntent ++ QueryModel.Intent.unresolvedPieces queryIntent
          }

data GroundShape
  = OrdinaryMetricShape
  | ObjectShape
  | TrendShape
  | ComparisonShape
  deriving (Show, Eq)

inferGroundShape :: QueryIntent -> GroundShape
inferGroundShape queryIntent
  | HintComparisonQuery `elem` queryShapeHints queryIntent = ComparisonShape
  | HintTrendQuery `elem` queryShapeHints queryIntent = TrendShape
  | HintObjectQuery `elem` queryShapeHints queryIntent = ObjectShape
  | otherwise = OrdinaryMetricShape

resolveSelectedMetric :: QueryIntent -> Either Text Text
resolveSelectedMetric queryIntent =
  case nub (metricMentions queryIntent) of
    [metricName] -> Right metricName
    [] -> Left "Could not ground a supported metric from the question."
    _ -> Left "The question matched multiple metrics ambiguously."

resolveTargetFilterKinds :: QueryIntent -> Either Text [Text]
resolveTargetFilterKinds queryIntent =
  case sort (map intentFilterKind (filters queryIntent)) of
    [] -> Left "Could not ground a supported filter bundle from the question."
    filterKinds -> Right filterKinds

intentFilterKind :: IntentFilter -> Text
intentFilterKind currentFilter =
  case currentFilter of
    IntentLastNGames _ -> "last_n_games"
    IntentExactSeason _ -> "exact_season"
    IntentSeasonType _ -> "season_type"
    IntentPastYear -> "past_year"

resolveDesiredRowObject :: QueryIntent -> GroundShape -> Maybe Text
resolveDesiredRowObject queryIntent shapeKind =
  case shapeKind of
    ObjectShape -> objectFromMentions
    ComparisonShape -> objectFromMentions
    _ -> Nothing
  where
    objectFromMentions =
      case objectMentions queryIntent of
        "Player" : _ -> Just "Player"
        "Team" : _ -> Just "Team"
        _ -> Nothing

resolveDesiredDimensions :: QueryIntent -> GroundShape -> Maybe Text -> [Text]
resolveDesiredDimensions queryIntent shapeKind maybeRowObject =
  case nub (dimensionMentions queryIntent) of
    [] ->
      case shapeKind of
        TrendShape -> []
        ComparisonShape ->
          case maybeRowObject of
            Just "Team" -> ["team_name"]
            _ -> ["player_name"]
        _ ->
          case maybeRowObject of
            Just "Player" -> ["player_name"]
            Just "Team" -> ["team_name"]
            Just _ -> []
            Nothing ->
              case objectMentions queryIntent of
                "Player" : _ -> ["player_name"]
                "Team" : _ -> ["team_name"]
                _ -> []
    dimensionValues -> dimensionValues

familyMatchesIntent ::
  GroundShape ->
  Text ->
  [Text] ->
  Maybe Text ->
  [Text] ->
  [LinkedFilterHint] ->
  QueryIntent ->
  DerivedFamily ->
  Bool
familyMatchesIntent shapeKind metricName targetFilterKinds maybeRowObject desiredDimensions desiredLinkedFilters queryIntent currentFamily =
  metricName `elem` metrics currentFamily
    && required_filter_kinds currentFamily == targetFilterKinds
    && dimensions currentFamily == desiredDimensions
    && rowObjectMatches
    && linkedFiltersMatch
    && timeGrainMatches
    && comparisonMatches
    && queryKindMatches
    && limitMatches
    && singleEntityIsAllowed
  where
    queryKindMatches =
      case shapeKind of
        ObjectShape -> query_kind currentFamily == "object_query"
        _ -> query_kind currentFamily == "metric_query"
    rowObjectMatches =
      case shapeKind of
        ObjectShape -> row_object currentFamily == maybeRowObject
        _ -> True
    linkedFiltersMatch =
      let familyLinkedFilters = linked_filters currentFamily
       in case desiredLinkedFilters of
            [] -> null familyLinkedFilters
            [LinkedFilterHint {targetObject = targetObjectName, attribute = attributeName}] ->
              familyLinkedFilters
                == [LinkedFilterCapability targetObjectName attributeName True]
            _ -> False
    timeGrainMatches =
      case shapeKind of
        TrendShape -> time_grain currentFamily == Just "month"
        _ -> time_grain currentFamily == Nothing
    comparisonMatches =
      case shapeKind of
        ComparisonShape ->
          case comparisonEntities queryIntent of
            [_firstEntity, _secondEntity] ->
              comparison currentFamily /= DerivedComparison False Nothing Nothing
                && comparison currentFamily == DerivedComparison True (desiredComparisonTarget maybeRowObject) (Just 2)
            _ -> False
        _ -> comparison currentFamily == DerivedComparison False Nothing Nothing
    limitMatches =
      case limitHint queryIntent of
        Just _ -> allow_limit currentFamily
        Nothing -> True
    singleEntityIsAllowed =
      null (singleEntityMentions queryIntent)

desiredComparisonTarget :: Maybe Text -> Maybe Text
desiredComparisonTarget maybeRowObject =
  case maybeRowObject of
    Just objectName -> Just objectName
    Nothing -> Just "Player"

rankCandidateFamilies :: GroundShape -> [Text] -> Maybe Text -> [LinkedFilterHint] -> [DerivedFamily] -> [DerivedFamily]
rankCandidateFamilies shapeKind targetFilterKinds maybeRowObject desiredLinkedFilters =
  map snd
    . reverse
    . sortOn fst
    . map
      ( \currentFamily ->
          ( familyScore shapeKind targetFilterKinds maybeRowObject desiredLinkedFilters currentFamily
          , currentFamily
          )
      )

familyScore :: GroundShape -> [Text] -> Maybe Text -> [LinkedFilterHint] -> DerivedFamily -> Int
familyScore shapeKind targetFilterKinds maybeRowObject desiredLinkedFilters currentFamily =
  baseScore
    + seasonPreference
    + recentPreference
    + trendPreference
    + rowPreference
    + linkedSurfacePreference
  where
    baseScore =
      (if query_kind currentFamily == "metric_query" then 30 else 0)
        + (if query_kind currentFamily == "object_query" then 30 else 0)
        + (if not (null desiredLinkedFilters) then 20 else 10)
    seasonPreference
      | targetFilterKinds == ["exact_season", "season_type"] =
          if core_fact_object currentFamily `elem` ["PlayerSeason", "TeamSeason"]
            then 40
            else
              if "Season" `T.isInfixOf` core_fact_object currentFamily
                then 20
                else 5
      | otherwise = 0
    recentPreference
      | targetFilterKinds == ["last_n_games"] =
          if "Game" `T.isInfixOf` core_fact_object currentFamily then 20 else 0
      | otherwise = 0
    trendPreference
      | shapeKind == TrendShape && null (dimensions currentFamily) =
          if core_fact_object currentFamily == "TeamGame" then 30 else 20
      | shapeKind == TrendShape = 10
      | otherwise = 0
    rowPreference =
      case maybeRowObject of
        Just rowObjectName ->
          if row_object currentFamily == Just rowObjectName
            then 15
            else 0
        Nothing -> 0
    linkedSurfacePreference
      | null desiredLinkedFilters && "SeasonTeam" `T.isSuffixOf` core_fact_object currentFamily = -20
      | null desiredLinkedFilters && "Game" `T.isSuffixOf` core_fact_object currentFamily && targetFilterKinds == ["exact_season", "season_type"] = -10
      | otherwise = 0

buildGroundedOrdering :: GroundShape -> Text -> Maybe GroundedOrdering
buildGroundedOrdering shapeKind metricName =
  case shapeKind of
    TrendShape -> Nothing
    ComparisonShape -> Nothing
    _ -> Just (GroundedOrdering (Just metricName) True)

groundComparisonIfNeeded :: QueryIntent -> DerivedFamily -> [Text] -> Either Text (Maybe GroundedComparison)
groundComparisonIfNeeded queryIntent currentFamily desiredDimensions =
  case inferGroundShape queryIntent of
    ComparisonShape ->
      case comparisonEntities queryIntent of
        [firstEntity, secondEntity] ->
          case comparison currentFamily of
            DerivedComparison True (Just targetObjectName) _ ->
              case desiredDimensions of
                [dimensionName] ->
                  Right
                    ( Just
                        GroundedComparison
                          { targetObject = targetObjectName
                          , identityDimension = dimensionName
                          , entityNames = [firstEntity, secondEntity]
                          }
                    )
                _ -> Left "Comparison grounding requires exactly one identity dimension."
            _ -> Left "No comparison-capable supported shape matched the question."
        _ -> Left "Comparison requires exactly two entity mentions."
    _ -> Right Nothing

groundedShapeFromFamily :: DerivedFamily -> GroundedQueryShape
groundedShapeFromFamily currentFamily =
  case query_kind currentFamily of
    "object_query" ->
      case row_object currentFamily of
        Just rowObjectName -> GroundedObjectQuery rowObjectName
        Nothing -> GroundedObjectQuery "UnknownRowObject"
    _ -> GroundedMetricQuery

intentFilterToGroundedFilter :: IntentFilter -> GroundedFilter
intentFilterToGroundedFilter currentFilter =
  case currentFilter of
    IntentLastNGames gamesValue ->
      GroundedFilter "last_n_games" (Just (QI.FilterInt gamesValue))
    IntentExactSeason seasonLabel ->
      GroundedFilter "exact_season" (Just (QI.FilterText seasonLabel))
    IntentSeasonType seasonTypeLabel ->
      GroundedFilter "season_type" (Just (QI.FilterText seasonTypeLabel))
    IntentPastYear ->
      GroundedFilter "past_year" Nothing

linkedFilterToGroundedFilter :: LinkedFilterHint -> GroundedLinkedFilter
linkedFilterToGroundedFilter linkedFilterHint =
  GroundedLinkedFilter
    { targetObject = QueryModel.Intent.targetObject linkedFilterHint
    , attribute = QueryModel.Intent.attribute linkedFilterHint
    , value = QueryModel.Intent.value linkedFilterHint
    }
