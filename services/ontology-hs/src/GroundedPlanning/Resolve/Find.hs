{-# LANGUAGE OverloadedStrings #-}

-- Purpose:
-- Ground find/filter+join queries into concrete runtime details.

module GroundedPlanning.Resolve.Find where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common
import OntologyLayer.Graph (DiscoveredPath, findAttribute)
import OntologyLayer.Types (Attribute (source_column), Object (backing_table), Ontology)
import QueryModel.IR

resolveFindQuery :: Ontology -> FindQuerySpec -> Either Text ResolvedFindQuery
resolveFindQuery ontology findQuery = do
  factObject <- requireObject ontology (findCoreFactObject findQuery)
  targetObjectValue <- requireObject ontology (findTargetObject findQuery)
  targetPathValue <- requirePath ontology (findCoreFactObject findQuery) (findTargetObject findQuery)
  displayValues <- mapM (resolveFindDisplay ontology targetObjectValue targetPathValue) (findDisplayDimensions findQuery)
  predicateTreeValue <- mapM (resolveFindPredicateTree ontology (findCoreFactObject findQuery)) (findPredicateTree findQuery)
  pure
    ResolvedFindQuery
      { resolvedFindFactTableName = backing_table factObject
      , resolvedFindTargetTableName = backing_table targetObjectValue
      , resolvedFindTargetObjectName = findTargetObject findQuery
      , resolvedFindTargetPath = targetPathValue
      , resolvedFindDisplays = displayValues
      , resolvedFindPredicateTree = predicateTreeValue
      , resolvedFindFilters = findFilters findQuery
      , resolvedFindLimit = findLimit findQuery
      , resolvedFindAssumptions = findAssumptions findQuery
      }

resolveFindDisplay :: Ontology -> Object -> DiscoveredPath -> DimensionName -> Either Text ResolvedFindDisplay
resolveFindDisplay _ontology targetObjectValue targetPathValue displayName = do
  attributeValue <-
    maybe
      (Left ("Could not resolve find display dimension '" <> displayName <> "'."))
      Right
      (findAttribute targetObjectValue displayName)
  pure
    ResolvedFindDisplay
      { displayPath = targetPathValue
      , displayColumn = source_column attributeValue
      , displayLabel = displayName
      }

canonicalizePredicateValue :: Attribute -> FilterValue -> FilterValue
canonicalizePredicateValue attributeValue predicateValue =
  case predicateValue of
    FilterText textValue ->
      FilterText (canonicalizeTextValue attributeValue textValue)
    FilterInt _ -> predicateValue
    FilterDouble _ -> predicateValue

resolveFindPredicateTree :: Ontology -> Text -> Predicate -> Either Text ResolvedFindPredicateTree
resolveFindPredicateTree ontology factObjectName predicateTree =
  case predicateTree of
    PredicateLeaf fieldValue operatorValue predicateValue ->
      ResolvedFindPredicateLeafNode <$> resolveFindPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue
    PredicateAnd predicateValues ->
      ResolvedFindPredicateAnd <$> mapM (resolveFindPredicateTree ontology factObjectName) predicateValues
    PredicateOr predicateValues ->
      ResolvedFindPredicateOr <$> mapM (resolveFindPredicateTree ontology factObjectName) predicateValues
    PredicateNot predicateValue ->
      ResolvedFindPredicateNot <$> resolveFindPredicateTree ontology factObjectName predicateValue

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
          canonicalizePredicateTreeValue
            attributeValue
            predicateValue
      }

canonicalizePredicateTreeValue :: Attribute -> PredicateValue -> PredicateValue
canonicalizePredicateTreeValue attributeValue predicateValue =
  case predicateValue of
    PredicateScalar scalarValue ->
      PredicateScalar (canonicalizePredicateValue attributeValue scalarValue)
    PredicateList values ->
      PredicateList (map (canonicalizePredicateValue attributeValue) values)
    PredicateRange lowerValue upperValue ->
      PredicateRange
        (canonicalizePredicateValue attributeValue lowerValue)
        (canonicalizePredicateValue attributeValue upperValue)
