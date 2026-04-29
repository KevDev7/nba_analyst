{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Dimensions
  ( requireAggregateGroupingDimensions
  , requireObjectQueryDimension
  , requireObjectQueryDimensionName
  , requireOrdinaryMetricDimension
  , requireOrdinaryMetricDimensionOnObject
  , requireOrdinaryMetricRowObject
  , requirePublicTrendDimensionOnObject
  , requireRankGroupingDimensions
  , requireTrendGroupingDimensions
  , requireReachableDimensionObject
  ) where

import Data.Text (Text)
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (AttributeKind (Dimension, PrimaryKey), AttributeVisibility (Public), Object, Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR (DimensionName)
import GroundedPlanning.Validation.Common.Ontology

requireOrdinaryMetricRowObject :: Ontology -> Object -> [DimensionName] -> Either Text Object
requireOrdinaryMetricRowObject ontology factObject dimensionValues = do
  dimensionName <- requireOrdinaryMetricDimension dimensionValues
  rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionName
  requireOrdinaryMetricDimensionOnObject rowObject dimensionName
  pure rowObject

requireAggregateGroupingDimensions :: Ontology -> Object -> [DimensionName] -> Either Text [Object]
requireAggregateGroupingDimensions ontology factObject dimensionValues =
  requireGroupingDimensionsWithMessage
    "Aggregate queries require at least one business grouping dimension."
    ontology
    factObject
    dimensionValues

requireRankGroupingDimensions :: Ontology -> Object -> [DimensionName] -> Either Text [Object]
requireRankGroupingDimensions ontology factObject dimensionValues =
  requireGroupingDimensionsWithMessage
    "Ranking queries require at least one business grouping dimension."
    ontology
    factObject
    dimensionValues

requireTrendGroupingDimensions :: Ontology -> Object -> [DimensionName] -> Either Text [Object]
requireTrendGroupingDimensions ontology factObject dimensionValues =
  requireGroupingDimensionsWithMessage
    "Trend queries require at least one business grouping dimension when dimensions are provided."
    ontology
    factObject
    dimensionValues

requireGroupingDimensionsWithMessage :: Text -> Ontology -> Object -> [DimensionName] -> Either Text [Object]
requireGroupingDimensionsWithMessage missingDimensionsMessage ontology factObject dimensionValues =
  case dimensionValues of
    [] -> Left missingDimensionsMessage
    _ -> mapM requireGroupableDimension dimensionValues
  where
    requireGroupableDimension dimensionName = do
      rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionName
      requireAggregateGroupingAttribute rowObject dimensionName
      pure rowObject

requireReachableDimensionObject :: Ontology -> Text -> DimensionName -> Either Text Object
requireReachableDimensionObject ontology factObjectName dimensionName = do
  let attributeName = dimensionName
  case firstLinkedObjectWithAttribute ontology factObjectName attributeName of
    Just objectValue -> Right objectValue
    Nothing ->
      case objectWithAttribute ontology factObjectName attributeName of
        Just objectValue -> Right objectValue
        Nothing ->
          Left
            ( "No valid ontology path from '"
                <> factObjectName
                <> "' reaches a displayed dimension attribute '"
                <> attributeName
                <> "'."
            )

requireOrdinaryMetricDimension :: [DimensionName] -> Either Text DimensionName
requireOrdinaryMetricDimension dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Ranking/aggregation metric queries require exactly one business grouping dimension."

requireObjectQueryDimensionName :: [DimensionName] -> Either Text DimensionName
requireObjectQueryDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Object queries require exactly one row dimension."

requireOrdinaryMetricDimensionOnObject :: Object -> DimensionName -> Either Text ()
requireOrdinaryMetricDimensionOnObject object dimensionName = do
  let attributeName = dimensionName
  requireAttributeKind object attributeName Dimension

requireAggregateGroupingAttribute :: Object -> DimensionName -> Either Text ()
requireAggregateGroupingAttribute object dimensionName = do
  attribute <-
    maybe
      (Left ("Attribute '" <> dimensionName <> "' not found in ontology."))
      Right
      (findAttribute object dimensionName)
  if OT.visibility attribute == Public && OT.kind attribute `elem` [Dimension, PrimaryKey]
    then pure ()
    else Left "Aggregate grouping supports public dimension or primary-key attributes only."

requireObjectQueryDimension :: Object -> [DimensionName] -> Either Text ()
requireObjectQueryDimension object dimensionValues = do
  dimensionName <- requireObjectQueryDimensionName dimensionValues
  let attributeName = dimensionName
  requireAttributeKind object attributeName Dimension

requirePublicTrendDimensionOnObject :: Object -> Text -> Either Text ()
requirePublicTrendDimensionOnObject object attributeName = do
  attribute <-
    maybe
      (Left ("Attribute '" <> attributeName <> "' not found in ontology."))
      Right
      (findAttribute object attributeName)
  if OT.kind attribute /= Dimension || OT.visibility attribute /= OT.Public
    then Left "Trend grouping supports reachable public dimension attributes only."
    else pure ()
