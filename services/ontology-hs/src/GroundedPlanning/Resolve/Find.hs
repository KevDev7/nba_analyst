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
  predicateValues <- mapM (resolveFindPredicate ontology (findCoreFactObject findQuery)) (findPredicates findQuery)
  pure
    ResolvedFindQuery
      { resolvedFindFactTableName = backing_table factObject
      , resolvedFindTargetTableName = backing_table targetObjectValue
      , resolvedFindTargetObjectName = findTargetObject findQuery
      , resolvedFindTargetPath = targetPathValue
      , resolvedFindDisplays = displayValues
      , resolvedFindPredicates = predicateValues
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

resolveFindPredicate :: Ontology -> Text -> FindPredicate -> Either Text ResolvedFindPredicate
resolveFindPredicate ontology factObjectName predicateValue = do
  predicatePathValue <- requirePath ontology factObjectName (predicateTargetObject predicateValue)
  predicateObject <- requireObject ontology (predicateTargetObject predicateValue)
  attributeValue <-
    maybe
      (Left ("Could not resolve find predicate attribute '" <> predicateAttribute predicateValue <> "'."))
      Right
      (findAttribute predicateObject (predicateAttribute predicateValue))
  pure
    ResolvedFindPredicate
      { predicatePath = predicatePathValue
      , predicateColumn = source_column attributeValue
      , predicateLabel = predicateAttribute predicateValue
      , predicateOp = predicateOpText (predicateOperator predicateValue)
      , predicateValue = predicateFilterValue predicateValue
      }
