{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Ground find/filter+join queries into concrete runtime details.

module GroundedPlanning.Resolve.Find where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common
import GroundedPlanning.Resolve.Common.PredicateTrees
import OntologyLayer.Graph (DiscoveredPath, findAllPathsFrom, findAttribute, findObject, findPath, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (Attribute (source_column), Object (backing_table), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

resolveFindQuery :: Ontology -> FindQuerySpec -> Either Text ResolvedFindQuery
resolveFindQuery ontology findQuery = do
  factObject <- requireObject ontology (findCoreFactObject findQuery)
  targetObjectValue <- requireObject ontology (findTargetObject findQuery)
  targetPathValue <- requirePath ontology (findCoreFactObject findQuery) (findTargetObject findQuery)
  displayValues <- mapM (resolveFindDisplay ontology factObject targetObjectValue targetPathValue) (findDisplayDimensions findQuery)
  orderValues <- mapM (resolveFindOrder ontology factObject targetObjectValue targetPathValue) (findOrders findQuery)
  predicateTreeValue <- mapM (resolveFindPredicateTree ontology (findCoreFactObject findQuery)) (findPredicateTree findQuery)
  pure
    ResolvedFindQuery
      { resolvedFindFactTableName = backing_table factObject
      , resolvedFindTargetTableName = backing_table targetObjectValue
      , resolvedFindTargetObjectName = findTargetObject findQuery
      , resolvedFindTargetPath = targetPathValue
      , resolvedFindDisplays = displayValues
      , resolvedFindOrders = orderValues
      , resolvedFindPredicateTree = predicateTreeValue
      , resolvedFindFilters = findFilters findQuery
      , resolvedFindLimit = findLimit findQuery
      , resolvedFindAssumptions = findAssumptions findQuery
      }

resolveFindDisplay :: Ontology -> Object -> Object -> DiscoveredPath -> FindDisplaySpec -> Either Text ResolvedFindDisplay
resolveFindDisplay ontology factObjectValue targetObjectValue targetPathValue displaySpec = do
  (displayPathValue, attributeValue) <-
    maybe
      (Left ("Could not resolve find display attribute '" <> findDisplayAttribute displaySpec <> "' against the selected fact object, target object, or reachable ontology links."))
      Right
      (findDisplayCandidate ontology factObjectValue targetObjectValue targetPathValue displaySpec)
  pure
    ResolvedFindDisplay
      { displayPath = displayPathValue
      , displayColumn = source_column attributeValue
      , displayLabel = findDisplayOutputLabel displaySpec
      }

findDisplayOutputLabel :: FindDisplaySpec -> Text
findDisplayOutputLabel displaySpec =
  case findDisplayLabel displaySpec of
    Just labelValue -> labelValue
    Nothing -> findDisplayAttribute displaySpec

findDisplayCandidate :: Ontology -> Object -> Object -> DiscoveredPath -> FindDisplaySpec -> Maybe (DiscoveredPath, OT.Attribute)
findDisplayCandidate ontology factObjectValue targetObjectValue targetPathValue displaySpec =
  case findDisplayCandidates ontology factObjectValue targetObjectValue targetPathValue displaySpec of
    candidate : _ -> Just candidate
    [] -> Nothing

findDisplayCandidates :: Ontology -> Object -> Object -> DiscoveredPath -> FindDisplaySpec -> [(DiscoveredPath, OT.Attribute)]
findDisplayCandidates ontology factObjectValue targetObjectValue targetPathValue displaySpec =
  case findDisplayLinkRole displaySpec of
    Just linkRoleValue ->
      roleLinkedCandidates linkRoleValue
    Nothing ->
      targetCandidates <> factCandidates <> linkedCandidates
  where
    displayName = findDisplayAttribute displaySpec
    targetCandidates =
      [ (targetPathValue, attributeValue)
      | Just attributeValue <- [findAttribute targetObjectValue displayName]
      , isPublicFindDisplayAttribute attributeValue
      , findDisplayTargetObject displaySpec `elem` [Nothing, Just (objectName targetObjectValue)]
      ]
    factCandidates =
      [ (factPathValue, attributeValue)
      | Just factPathValue <- [findPath ontology 2 (objectName factObjectValue) (objectName factObjectValue)]
      , Just attributeValue <- [findAttribute factObjectValue displayName]
      , isPublicFindDisplayAttribute attributeValue
      , findDisplayTargetObject displaySpec `elem` [Nothing, Just (objectName factObjectValue)]
      ]
    linkedCandidates =
      [ (discoveredPath, attributeValue)
      | discoveredPath <- findPathsFrom ontology 2 (objectName factObjectValue)
      , OG.targetObjectName discoveredPath /= objectName targetObjectValue
      , Just linkedObject <- [findObject ontology (OG.targetObjectName discoveredPath)]
      , Just attributeValue <- [findAttribute linkedObject displayName]
      , isPublicFindDisplayAttribute attributeValue
      , findDisplayTargetObject displaySpec `elem` [Nothing, Just (objectName linkedObject)]
      ]
    roleLinkedCandidates linkRoleValue =
      [ (discoveredPath, attributeValue)
      | discoveredPath <- findAllPathsFrom ontology 2 (objectName factObjectValue)
      , lastLinkName discoveredPath == linkRoleValue
      , Just linkedObject <- [findObject ontology (OG.targetObjectName discoveredPath)]
      , findDisplayTargetObject displaySpec `elem` [Nothing, Just (objectName linkedObject)]
      , Just attributeValue <- [findAttribute linkedObject displayName]
      , isPublicFindDisplayAttribute attributeValue
      ]

lastLinkName :: DiscoveredPath -> Text
lastLinkName pathValue =
  case reverse (OG.steps pathValue) of
    stepValue : _ -> OG.linkName stepValue
    [] -> ""

isPublicFindDisplayAttribute :: OT.Attribute -> Bool
isPublicFindDisplayAttribute attributeValue =
  OT.visibility attributeValue == OT.Public
    && OT.kind attributeValue `elem` [OT.Dimension, OT.Measure]

resolveFindOrder :: Ontology -> Object -> Object -> DiscoveredPath -> FindOrderSpec -> Either Text ResolvedFindOrder
resolveFindOrder ontology factObjectValue targetObjectValue targetPathValue orderSpec = do
  (orderPathValue, attributeValue) <-
    maybe
      (Left ("Could not resolve find order attribute '" <> findDisplayAttribute (findOrderField orderSpec) <> "' against the selected fact object, target object, or reachable ontology links."))
      Right
      (findDisplayCandidate ontology factObjectValue targetObjectValue targetPathValue (findOrderField orderSpec))
  pure
    ResolvedFindOrder
      { orderPath = orderPathValue
      , orderColumn = source_column attributeValue
      , orderLabel = findDisplayOutputLabel (findOrderField orderSpec)
      , orderDirection = findOrderDirection orderSpec
      }

resolveFindPredicateTree :: Ontology -> Text -> Predicate -> Either Text ResolvedFindPredicateTree
resolveFindPredicateTree ontology factObjectName predicateTree =
  resolvePredicateTree
    (resolveFindPredicateLeaf ontology factObjectName)
    ResolvedFindPredicateLeafNode
    ResolvedFindPredicateAnd
    ResolvedFindPredicateOr
    ResolvedFindPredicateNot
    predicateTree

resolveFindPredicateLeaf :: Ontology -> Text -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ResolvedFindPredicateLeaf
resolveFindPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue = do
  predicatePathValue <- requirePath ontology factObjectName (predicateFieldTargetObject fieldValue)
  predicateObject <- requireObject ontology (predicateFieldTargetObject fieldValue)
  attributeValue <-
    maybe
      (Left ("Could not resolve find predicate attribute '" <> predicateFieldAttribute fieldValue <> "'."))
      Right
      (findAttribute predicateObject (predicateFieldAttribute fieldValue))
  pure
    ResolvedFindPredicateLeaf
      { treePredicateTargetObjectName = predicateFieldTargetObject fieldValue
      , treePredicatePath = predicatePathValue
      , treePredicateColumn = source_column attributeValue
      , treePredicateLabel = predicateFieldAttribute fieldValue
      , treePredicateOperator = operatorValue
      , treePredicateValue =
          canonicalizePredicateTreeValue attributeValue predicateValue
      }
