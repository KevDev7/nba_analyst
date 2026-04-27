{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Dimensions
  ( emptyPath
  , firstLinkedObjectWithAttribute
  , metricDisplayColumn
  , objectPrimaryKey
  , pathPartitionKey
  , requireAnySingleDimensionName
  , requireComparisonDimensionName
  , requireOrdinaryMetricDimensionName
  , resolveComparisonRowObject
  , resolveOrdinaryMetricRowObject
  ) where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common.Ontology
import GroundedPlanning.Resolve.Common.Types
import OntologyLayer.Graph (DiscoveredPath (steps), findObject, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (Attribute (source_column), AttributeKind (PrimaryKey), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

resolveOrdinaryMetricRowObject :: Ontology -> Text -> [DimensionName] -> Either Text (OT.Object, DiscoveredPath)
resolveOrdinaryMetricRowObject ontology factObjectName dimensionValues = do
  dimensionName <- requireOrdinaryMetricDimensionName dimensionValues
  let attributeName = dimensionName
  case firstLinkedObjectWithAttribute ontology factObjectName attributeName [] of
    Just resolvedValue -> Right resolvedValue
    Nothing -> do
      factObject <- requireObject ontology factObjectName
      if hasAttribute factObject attributeName
        then Right (factObject, emptyPath factObjectName)
        else Left ("Could not resolve a reachable row object for ranking/aggregation dimension '" <> attributeName <> "'.")

resolveComparisonRowObject :: Ontology -> Text -> [DimensionName] -> Maybe Text -> Either Text (OT.Object, DiscoveredPath)
resolveComparisonRowObject ontology factObjectName dimensionValues maybeTargetObjectName = do
  dimensionName <- requireComparisonDimensionName dimensionValues
  let attributeName = dimensionName
  case maybeTargetObjectName of
    Just targetObjectName -> do
      targetObject <- requireObject ontology targetObjectName
      discoveredPath <-
        if targetObjectName == factObjectName
          then Right (emptyPath factObjectName)
          else requirePath ontology factObjectName targetObjectName
      if hasAttribute targetObject attributeName
        then Right (targetObject, discoveredPath)
        else Left ("Could not resolve comparison identity dimension '" <> attributeName <> "' on target object '" <> targetObjectName <> "'.")
    Nothing ->
      case firstLinkedObjectWithAttribute ontology factObjectName attributeName [] of
        Just resolvedValue -> Right resolvedValue
        Nothing -> do
          factObject <- requireObject ontology factObjectName
          if hasAttribute factObject attributeName
            then Right (factObject, emptyPath factObjectName)
            else Left ("Could not resolve a reachable row object for comparison dimension '" <> attributeName <> "'.")

firstLinkedObjectWithAttribute :: Ontology -> Text -> Text -> [Text] -> Maybe (OT.Object, DiscoveredPath)
firstLinkedObjectWithAttribute ontology factObjectName attributeName excludedObjectNames =
  -- Temporary planner restriction. Like validation, this helper only searches
  -- depth-2 ontology paths for the current slices.
  case
    [ (objectValue, discoveredPath)
    | discoveredPath <- findPathsFrom ontology 2 factObjectName
    , let targetObjectNameValue = OG.targetObjectName discoveredPath
    , targetObjectNameValue `notElem` excludedObjectNames
    , Just objectValue <- [findObject ontology targetObjectNameValue]
    , hasAttribute objectValue attributeName
    ]
    of
    resolvedValue : _ -> Just resolvedValue
    [] -> Nothing

emptyPath :: Text -> DiscoveredPath
emptyPath objectNameValue =
  OG.DiscoveredPath
    { OG.sourceObjectName = objectNameValue
    , OG.targetObjectName = objectNameValue
    , OG.steps = []
    }

pathPartitionKey :: Text -> DiscoveredPath -> ColumnRef
pathPartitionKey fallbackColumn discoveredPath =
  case steps discoveredPath of
    firstStep : _ -> ColumnRef "fact" (OG.sourceKey firstStep)
    [] -> ColumnRef "fact" fallbackColumn

objectPrimaryKey :: OT.Object -> Either Text Text
objectPrimaryKey objectValue =
  case
    [ source_column attribute
    | attribute <- OT.attributes objectValue
    , OT.kind attribute == PrimaryKey
    ]
    of
    primaryKeyColumn : _ -> Right primaryKeyColumn
    [] -> Left ("Object '" <> objectName objectValue <> "' does not expose a primary key in the ontology.")

metricDisplayColumn :: [DimensionName] -> Either Text Text
metricDisplayColumn dimensionValues = do
  dimensionName <- requireAnySingleDimensionName dimensionValues
  pure dimensionName

requireAnySingleDimensionName :: [DimensionName] -> Either Text DimensionName
requireAnySingleDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Current runtime result shapes require exactly one selected dimension."

requireOrdinaryMetricDimensionName :: [DimensionName] -> Either Text DimensionName
requireOrdinaryMetricDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Ranking/aggregation metric queries require exactly one business grouping dimension."

requireComparisonDimensionName :: [DimensionName] -> Either Text DimensionName
requireComparisonDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Comparison queries require exactly one business grouping dimension."
