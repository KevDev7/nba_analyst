{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Comparison
  ( comparisonRuntimeMetricSupported
  , requireComparisonDimensionOnObject
  , requireComparisonRowObject
  , requireComparisonTargetObject
  , requireComparisonTargetPath
  , validateComparisonEntities
  , validateComparisonMetric
  , validateComparisonPath
  , validateComparisonQuery
  , validateComparisonQueryShape
  ) where

import Data.List (nub)
import Data.Text (Text)
import OntologyLayer.Graph (DiscoveredPath, findAttribute)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (AttributeKind (Dimension), MetricDef (aggregation, executable, source_attributes), Object, Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR
import GroundedPlanning.Validation.Common.Dimensions (requireAggregateGroupingDimensions)
import GroundedPlanning.Validation.Common.Filters (classifyOrdinaryMetricFilterFamily, hasSeasonFilters, isExactSeasonBundle)
import GroundedPlanning.Validation.Common.Ontology
import GroundedPlanning.Validation.Common.RowPredicates (validateRowPredicateTree)
import GroundedPlanning.Validation.Common.Trend (validateTrendFactSurface, validateTrendTimeGrain)

requireComparisonRowObject :: Ontology -> Object -> [DimensionName] -> ComparisonIntent -> Either Text Object
requireComparisonRowObject ontology factObject dimensionValues comparisonIntent = do
  dimensionName <- requireComparisonDimension dimensionValues
  rowObject <- requireComparisonTargetObject ontology factObject comparisonIntent
  requireComparisonDimensionOnObject rowObject dimensionName
  pure rowObject

requireComparisonDimension :: [DimensionName] -> Either Text DimensionName
requireComparisonDimension dimensionValues =
  case dimensionValues of
    dimensionValue : _ -> Right dimensionValue
    [] -> Left "Comparison queries require a comparison identity dimension."

validateComparisonQuery :: Ontology -> Object -> Object -> [OT.MetricDef] -> BaseQuery -> ComparisonIntent -> [EntityRef] -> Either Text ()
validateComparisonQuery ontology factObject rowObject metricDefs base comparisonIntent entityRefs = do
  validateComparisonQueryShape base
  validateComparisonSeasonAttributes factObject base
  validateComparisonTimeGrain factObject (timeGrain base)
  validateComparisonBreakdownDimensions ontology factObject (drop 1 (dimensions base))
  mapM_ (validateRowPredicateTree ontology (objectName factObject)) (rowPredicate base)
  validateNoComparisonResultPredicate (resultPredicate base)
  validateComparisonPath ontology factObject rowObject comparisonIntent
  mapM_ (validateComparisonMetric base) metricDefs
  validateComparisonEntities entityRefs

validateComparisonQueryShape :: BaseQuery -> Either Text ()
validateComparisonQueryShape base = do
  if null (orders base)
    then pure ()
    else Left "Comparison queries should not request ranking order."
  case limit base of
    Nothing -> pure ()
    Just _ -> Left "Comparison queries do not support limit."
  case classifyOrdinaryMetricFilterFamily (filters base) of
    Right _ -> pure ()
    Left errorMessage -> Left errorMessage
  case dimensions base of
    _ : _ -> pure ()
    [] -> Left "Comparison queries require a comparison identity dimension."

validateComparisonTimeGrain :: Object -> Maybe TimeGrain -> Either Text ()
validateComparisonTimeGrain factObject maybeTimeGrain =
  case maybeTimeGrain of
    Nothing -> pure ()
    Just timeGrainValue -> do
      validateTrendTimeGrain timeGrainValue
      validateTrendFactSurface factObject timeGrainValue

validateComparisonBreakdownDimensions :: Ontology -> Object -> [DimensionName] -> Either Text ()
validateComparisonBreakdownDimensions ontology factObject dimensionValues =
  case dimensionValues of
    [] -> pure ()
    _ -> do
      _ <- requireAggregateGroupingDimensions ontology factObject dimensionValues
      pure ()

validateComparisonPath :: Ontology -> Object -> Object -> ComparisonIntent -> Either Text ()
validateComparisonPath ontology factObject rowObject comparisonIntent = do
  _ <- requireComparisonTargetPath ontology factObject rowObject comparisonIntent
  pure ()

validateComparisonMetric :: BaseQuery -> OT.MetricDef -> Either Text ()
validateComparisonMetric base metricDef =
  if comparisonRuntimeMetricSupported base metricDef
    then pure ()
    else Left "Comparison supports executable sum/avg metrics for recent rows and executable identity metrics for season surfaces."

validateComparisonEntities :: [EntityRef] -> Either Text ()
validateComparisonEntities entityRefs =
  if length entityRefs < 2 || length (nub (map entityId entityRefs)) /= length entityRefs
    then Left "Comparison requires at least two distinct supported entities."
    else pure ()

validateComparisonSeasonAttributes :: Object -> BaseQuery -> Either Text ()
validateComparisonSeasonAttributes factObject base =
  if hasSeasonFilters (filters base)
    then do
      requireFactAttribute factObject "season_year" "Season-scoped comparison queries require a season_year attribute on the fact object."
      requireFactAttribute factObject "season_type" "Season-scoped comparison queries require a season_type attribute on the fact object."
    else pure ()

requireComparisonDimensionOnObject :: Object -> DimensionName -> Either Text ()
requireComparisonDimensionOnObject object dimensionName = do
  attribute <-
    maybe
      (Left ("Attribute '" <> dimensionName <> "' not found in ontology."))
      Right
      (findAttribute object dimensionName)
  if OT.kind attribute /= Dimension || OT.visibility attribute /= OT.Public
    then Left "Comparison queries support public comparison identity dimensions only."
    else
      if OT.comparison_identity attribute
        then pure ()
        else Left "Comparison queries require a comparison identity dimension on the target object."

requireComparisonTargetObject :: Ontology -> Object -> ComparisonIntent -> Either Text Object
requireComparisonTargetObject ontology factObject comparisonIntent =
  case comparisonIntent of
    CompareEntities targetObjectName _ -> do
      targetObject <- requireObject ontology targetObjectName
      _ <- requireComparisonTargetPath ontology factObject targetObject comparisonIntent
      pure targetObject

requireComparisonTargetPath :: Ontology -> Object -> Object -> ComparisonIntent -> Either Text DiscoveredPath
requireComparisonTargetPath ontology factObject rowObject comparisonIntent =
  case comparisonIntent of
    CompareEntities targetObjectName _ ->
      if targetObjectName /= objectName rowObject
        then Left "Comparison target object and resolved comparison row object must match."
        else
          if targetObjectName == objectName factObject
            then Right (OG.DiscoveredPath (objectName factObject) (objectName factObject) [])
            else requirePath ontology (objectName factObject) targetObjectName

comparisonRuntimeMetricSupported :: BaseQuery -> OT.MetricDef -> Bool
comparisonRuntimeMetricSupported base metricDef =
  executable metricDef
    && if isExactSeasonBundle (filters base) && timeGrain base == Nothing
      then aggregation metricDef `elem` ["identity"]
      else aggregation metricDef `elem` ["sum", "avg", "count_win", "count_loss", "count_true"]
    && length (source_attributes metricDef) == 1

validateNoComparisonResultPredicate :: Maybe Predicate -> Either Text ()
validateNoComparisonResultPredicate maybePredicate =
  case maybePredicate of
    Nothing -> pure ()
    Just _ -> Left "Comparison result predicates are not supported because comparison results are computed after SQL execution."
