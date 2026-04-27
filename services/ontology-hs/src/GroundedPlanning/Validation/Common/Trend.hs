{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Trend
  ( requireDerivedTrendBucket
  , trendFactSurfaceMessage
  , validateObjectQueryTimeGrain
  , validateTrendDimensions
  , validateTrendFactSurface
  , validateTrendFilters
  , validateTrendLimit
  , validateTrendMetricQuery
  , validateTrendTimeGrain
  ) where

import Data.List (nub)
import Data.Text (Text)
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (AttributeKind (Dimension), Object, Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR
import GroundedPlanning.Validation.Common.Dimensions
import GroundedPlanning.Validation.Common.LinkedFilters
import GroundedPlanning.Validation.Common.Ontology
import GroundedPlanning.Validation.Common.Orders

validateTrendMetricQuery :: Ontology -> Object -> OT.MetricDef -> TimeGrain -> BaseQuery -> Either Text ()
validateTrendMetricQuery ontology factObject _metricDef timeGrainValue base = do
  validateTrendTimeGrain timeGrainValue
  validateTrendFilters factObject (filters base)
  validateTrendLimit (limit base)
  validateLinkedFilters ontology (objectName factObject) (linkedFilters base)
  validateTrendOrders (orders base)
  validateTrendFactSurface factObject timeGrainValue
  validateTrendDimensions ontology factObject (dimensions base)

validateTrendFilters :: Object -> [Filter] -> Either Text ()
validateTrendFilters factObject filterValues = do
  if length filterKinds == length (nub filterKinds)
    then pure ()
    else Left "Trend queries do not support duplicate filter kinds."
  mapM_ validateTrendFilter filterValues
  where
    filterKinds = map filterKindText filterValues
    validateTrendFilter filterValue =
      case filterKindText filterValue of
        "past_year" -> do
          requireFactAttribute factObject "game_date" "Past-year trend filters require an ontology-backed game_date attribute."
          pure ()
        "season_type" ->
          case filterTextValue filterValue of
            Just _ -> do
              requireFactAttribute factObject "season_type" "Season-type trend filters require an ontology-backed season_type attribute."
              pure ()
            Nothing -> Left "Season-type trend filters require a text value."
        _ -> Left ("Unsupported trend filter kind '" <> filterKindText filterValue <> "'.")

validateTrendTimeGrain :: TimeGrain -> Either Text ()
validateTrendTimeGrain timeGrainValue =
  if timeGrainText timeGrainValue `elem` ["day", "week", timeGrainText monthTimeGrain, "season"]
    then pure ()
    else Left "Trend queries support calendar day, week, month, or season grains."

validateObjectQueryTimeGrain :: Maybe TimeGrain -> Either Text ()
validateObjectQueryTimeGrain maybeTimeGrain =
  case maybeTimeGrain of
    Nothing -> pure ()
    Just _ -> Left "Object queries do not support time-grain trends."

validateTrendLimit :: Maybe Int -> Either Text ()
validateTrendLimit maybeLimit =
  case maybeLimit of
    Nothing -> pure ()
    Just _ -> Left "Trend queries do not support limit."

validateTrendFactSurface :: Object -> TimeGrain -> Either Text ()
validateTrendFactSurface factObject timeGrainValue =
  case timeGrainText timeGrainValue of
    "day" -> requireFactAttribute factObject "game_date" trendFactSurfaceMessage
    "week" -> requireFactAttribute factObject "game_date" trendFactSurfaceMessage
    "month" -> requireFactAttribute factObject "game_date" trendFactSurfaceMessage
    "season" -> requireFactAttribute factObject "season_year" "Season trend queries require an ontology-backed season_year attribute."
    _ -> Left "Trend queries support calendar day, week, month, or season grains."

validateTrendDimensions :: Ontology -> Object -> [DimensionName] -> Either Text ()
validateTrendDimensions ontology factObject dimensionValues =
  case dimensionValues of
    [] -> pure ()
    [dimensionValue] -> do
      rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionValue
      requirePublicTrendDimensionOnObject rowObject dimensionValue
      pure ()
    _ -> Left "Trend queries support at most one business grouping dimension."

trendFactSurfaceMessage :: Text
trendFactSurfaceMessage =
  "Trend queries require a fact surface that exposes an ontology-backed game_date attribute."

requireDerivedTrendBucket :: Object -> Text -> Either Text ()
requireDerivedTrendBucket object attributeName = do
  attribute <-
    maybe
      (Left trendFactSurfaceMessage)
      Right
      (findAttribute object attributeName)
  if OT.kind attribute /= Dimension || OT.derivation attribute == Nothing
    then Left trendFactSurfaceMessage
    else pure ()
