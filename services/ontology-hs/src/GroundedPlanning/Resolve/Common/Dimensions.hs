{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Dimensions
  ( emptyPath
  , firstLinkedObjectWithAttribute
  , metricDisplayColumn
  , objectPrimaryKey
  , pathPartitionKey
  , requireAnySingleDimensionName
  , requireComparisonBreakdownDimensionNames
  , requireComparisonDimensionName
  , requireOrdinaryMetricDimensionName
  , resolveAggregateGroupingDimensions
  , resolveComparisonRowObject
  , resolveOrdinaryMetricRowObject
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Resolve.Common.Ontology
import GroundedPlanning.Resolve.Common.Types
import OntologyLayer.Graph (DiscoveredPath (steps), findAttribute, findObject, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (Attribute (source_column), AttributeKind (Dimension, PrimaryKey), AttributeVisibility (Public), Ontology)
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

resolveAggregateGroupingDimensions :: Ontology -> Text -> [DimensionName] -> Either Text [(OT.Object, DiscoveredPath, ResolvedGroupingDimension)]
resolveAggregateGroupingDimensions ontology factObjectName dimensionValues =
  case dimensionValues of
    [] -> Left "Aggregate queries require at least one business grouping dimension."
    _ -> mapM resolveIndexedGroupingDimension (zip [1 :: Int ..] dimensionValues)
  where
    resolveIndexedGroupingDimension (indexValue, dimensionName) = do
      (groupObject, groupPath) <- resolveReachableGroupingObject dimensionName
      attribute <-
        maybe
          (Left ("Could not resolve aggregate grouping attribute '" <> dimensionName <> "'."))
          Right
          (findAttribute groupObject dimensionName)
      if OT.visibility attribute == Public && OT.kind attribute `elem` [Dimension, PrimaryKey]
        then
          let sourceRole =
                if null (steps groupPath)
                  then "fact"
                  else "group"
              groupingDimension =
                ResolvedGroupingDimension
                  { groupingKey = "group_" <> T.pack (show indexValue)
                  , groupingLabel = dimensionName
                  , groupingPath = groupPath
                  , groupingSource = ColumnRef sourceRole (source_column attribute)
                  }
           in Right (groupObject, groupPath, groupingDimension)
        else Left "Aggregate grouping supports public dimension or primary-key attributes only."

    resolveReachableGroupingObject dimensionName =
      do
        factObject <- requireObject ontology factObjectName
        if hasAttribute factObject dimensionName
          then Right (factObject, emptyPath factObjectName)
          else
            case firstLinkedObjectWithAttribute ontology factObjectName dimensionName [] of
              Just resolvedValue -> Right resolvedValue
              Nothing -> Left ("Could not resolve a reachable grouping object for aggregate dimension '" <> dimensionName <> "'.")

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
    dimensionValue : _ -> Right dimensionValue
    [] -> Left "Comparison queries require a comparison identity dimension."

requireComparisonBreakdownDimensionNames :: [DimensionName] -> [DimensionName]
requireComparisonBreakdownDimensionNames dimensionValues =
  case dimensionValues of
    _identityDimension : breakdownDimensions -> breakdownDimensions
    [] -> []
