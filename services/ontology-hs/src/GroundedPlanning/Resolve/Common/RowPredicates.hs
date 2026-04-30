{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.RowPredicates
  ( planRowPredicateTree
  , resolveBaseRowPredicate
  ) where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common.Ontology
import GroundedPlanning.Resolve.Common.PredicateTrees
import GroundedPlanning.Resolve.Common.Types
import OntologyLayer.Graph (findAttribute, findPathByLastLinkName)
import OntologyLayer.Types (Attribute (source_column), Ontology)
import QueryModel.IR

resolveBaseRowPredicate :: Ontology -> Text -> Maybe Predicate -> Either Text (Maybe ResolvedRowPredicateTree)
resolveBaseRowPredicate ontology factObjectName maybeRowPredicate =
  mapM (resolveRowPredicateTree ontology factObjectName) maybeRowPredicate

resolveRowPredicateTree :: Ontology -> Text -> Predicate -> Either Text ResolvedRowPredicateTree
resolveRowPredicateTree ontology factObjectName predicateTree =
  resolvePredicateTree
    (resolveRowPredicateLeaf ontology factObjectName)
    ResolvedRowPredicateLeafNode
    ResolvedRowPredicateAnd
    ResolvedRowPredicateOr
    ResolvedRowPredicateNot
    predicateTree

resolveRowPredicateLeaf :: Ontology -> Text -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ResolvedRowPredicateLeaf
resolveRowPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue = do
  predicatePathValue <-
    case predicateFieldLinkRole fieldValue of
      Just linkRoleValue ->
        maybe
          (Left ("Could not resolve an ontology path from '" <> factObjectName <> "' to '" <> predicateFieldTargetObject fieldValue <> "' through link role '" <> linkRoleValue <> "'."))
          Right
          (findPathByLastLinkName ontology 2 factObjectName (predicateFieldTargetObject fieldValue) linkRoleValue)
      Nothing -> requirePath ontology factObjectName (predicateFieldTargetObject fieldValue)
  predicateObject <- requireObject ontology (predicateFieldTargetObject fieldValue)
  attributeValue <-
    maybe
      (Left ("Could not resolve row predicate attribute '" <> predicateFieldAttribute fieldValue <> "' against the ontology."))
      Right
      (findAttribute predicateObject (predicateFieldAttribute fieldValue))
  pure
    ResolvedRowPredicateLeaf
      { rowPredicateTargetObjectName = predicateFieldTargetObject fieldValue
      , rowPredicatePath = predicatePathValue
      , rowPredicateColumn = source_column attributeValue
      , rowPredicateLabel = predicateFieldAttribute fieldValue
      , rowPredicateOperator = operatorValue
      , rowPredicateValue =
          canonicalizePredicateTreeValue attributeValue predicateValue
      }

planRowPredicateTree :: ResolvedRowPredicateTree -> Predicate
planRowPredicateTree predicateTree =
  case predicateTree of
    ResolvedRowPredicateLeafNode predicateLeaf ->
      PredicateLeaf
        PredicateField
          { predicateFieldTargetObject = rowPredicateTargetObjectName predicateLeaf
          , predicateFieldAttribute = rowPredicateLabel predicateLeaf
          , predicateLocation = PredicateRowField
          , predicateFieldLinkRole = Nothing
          , predicateFieldLabel = Nothing
          }
        (rowPredicateOperator predicateLeaf)
        (rowPredicateValue predicateLeaf)
    ResolvedRowPredicateAnd predicateValues ->
      PredicateAnd (map planRowPredicateTree predicateValues)
    ResolvedRowPredicateOr predicateValues ->
      PredicateOr (map planRowPredicateTree predicateValues)
    ResolvedRowPredicateNot predicateValue ->
      PredicateNot (planRowPredicateTree predicateValue)
