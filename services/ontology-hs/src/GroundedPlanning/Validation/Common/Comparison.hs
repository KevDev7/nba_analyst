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
import GroundedPlanning.Validation.Common.Ontology

requireComparisonRowObject :: Ontology -> Object -> [DimensionName] -> ComparisonIntent -> Either Text Object
requireComparisonRowObject ontology factObject dimensionValues comparisonIntent = do
  dimensionName <- requireComparisonDimension dimensionValues
  rowObject <- requireComparisonTargetObject ontology factObject comparisonIntent
  requireComparisonDimensionOnObject rowObject dimensionName
  pure rowObject

requireComparisonDimension :: [DimensionName] -> Either Text DimensionName
requireComparisonDimension dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Comparison queries require exactly one business grouping dimension."

validateComparisonQuery :: Ontology -> Object -> Object -> OT.MetricDef -> BaseQuery -> ComparisonIntent -> [EntityRef] -> Either Text ()
validateComparisonQuery ontology factObject rowObject metricDef base comparisonIntent entityRefs = do
  validateComparisonQueryShape base
  validateLinkedFiltersForComparison ontology (objectName factObject) (linkedFilters base)
  validateComparisonPath ontology factObject rowObject comparisonIntent
  validateComparisonMetric metricDef
  validateComparisonEntities entityRefs

validateComparisonQueryShape :: BaseQuery -> Either Text ()
validateComparisonQueryShape base = do
  if null (orders base)
    then pure ()
    else Left "Comparison queries should not request ranking order."
  case limit base of
    Nothing -> pure ()
    Just _ -> Left "Comparison queries do not support limit."
  case timeGrain base of
    Nothing -> pure ()
    Just _ -> Left "Comparison queries do not support time-grain trends."
  case filters base of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue
      , gamesValue > 0 -> pure ()
    _ -> Left "Comparison queries require a positive LastNGames filter."
  case dimensions base of
    [_] -> pure ()
    _ -> Left "Comparison queries require exactly one comparison identity dimension."

validateComparisonPath :: Ontology -> Object -> Object -> ComparisonIntent -> Either Text ()
validateComparisonPath ontology factObject rowObject comparisonIntent = do
  _ <- requireComparisonTargetPath ontology factObject rowObject comparisonIntent
  pure ()

validateComparisonMetric :: OT.MetricDef -> Either Text ()
validateComparisonMetric metricDef =
  if comparisonRuntimeMetricSupported metricDef
    then pure ()
    else Left "Comparison supports executable sum/avg metrics over recent row-level values only."

validateComparisonEntities :: [EntityRef] -> Either Text ()
validateComparisonEntities entityRefs =
  if length entityRefs < 2 || length (nub (map entityId entityRefs)) /= length entityRefs
    then Left "Comparison requires at least two distinct supported entities."
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

comparisonRuntimeMetricSupported :: OT.MetricDef -> Bool
comparisonRuntimeMetricSupported metricDef =
  executable metricDef
    && aggregation metricDef `elem` ["sum", "avg"]
    && length (source_attributes metricDef) == 1

validateLinkedFiltersForComparison :: Ontology -> Text -> [LinkedFilter] -> Either Text ()
validateLinkedFiltersForComparison ontology factObjectName linkedFilterValues =
  mapM_ validateLinkedFilter linkedFilterValues
  where
    validateLinkedFilter linkedFilterValue = do
      _ <- requirePath ontology factObjectName (targetObject linkedFilterValue)
      targetObjectValue <- requireObject ontology (targetObject linkedFilterValue)
      attribute <-
        maybe
          (Left ("Linked filters support public dimension attributes on reachable ontology objects only."))
          Right
          (findAttribute targetObjectValue (attribute linkedFilterValue))
      if OT.kind attribute /= Dimension || OT.visibility attribute /= OT.Public
        then Left "Linked filters support public dimension attributes on reachable ontology objects only."
        else pure ()
