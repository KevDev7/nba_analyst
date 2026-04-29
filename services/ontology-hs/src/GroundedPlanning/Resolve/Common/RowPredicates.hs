{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.RowPredicates
  ( planRowPredicateTree
  , resolveBaseRowPredicate
  ) where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common.Ontology
import GroundedPlanning.Resolve.Common.Types
import GroundedPlanning.Resolve.Common.ValueCanonicalization
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (Attribute (source_column), Ontology)
import QueryModel.IR

resolveBaseRowPredicate :: Ontology -> Text -> Maybe Predicate -> Either Text (Maybe ResolvedRowPredicateTree)
resolveBaseRowPredicate ontology factObjectName maybeRowPredicate =
  mapM (resolveRowPredicateTree ontology factObjectName) maybeRowPredicate

resolveRowPredicateTree :: Ontology -> Text -> Predicate -> Either Text ResolvedRowPredicateTree
resolveRowPredicateTree ontology factObjectName predicateTree =
  case predicateTree of
    PredicateLeaf fieldValue operatorValue predicateValue ->
      ResolvedRowPredicateLeafNode <$> resolveRowPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue
    PredicateAnd predicateValues ->
      ResolvedRowPredicateAnd <$> mapM (resolveRowPredicateTree ontology factObjectName) predicateValues
    PredicateOr predicateValues ->
      ResolvedRowPredicateOr <$> mapM (resolveRowPredicateTree ontology factObjectName) predicateValues
    PredicateNot predicateValue ->
      ResolvedRowPredicateNot <$> resolveRowPredicateTree ontology factObjectName predicateValue

resolveRowPredicateLeaf :: Ontology -> Text -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ResolvedRowPredicateLeaf
resolveRowPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue = do
  predicatePathValue <- requirePath ontology factObjectName (predicateFieldTargetObject fieldValue)
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
          canonicalizePredicateTreeValue
            attributeValue
            predicateValue
      }

canonicalizePredicateTreeValue :: Attribute -> PredicateValue -> PredicateValue
canonicalizePredicateTreeValue attributeValue predicateValue =
  case predicateValue of
    PredicateScalar scalarValue ->
      PredicateScalar (canonicalizePredicateScalar attributeValue scalarValue)
    PredicateList values ->
      PredicateList (map (canonicalizePredicateScalar attributeValue) values)
    PredicateRange lowerValue upperValue ->
      PredicateRange
        (canonicalizePredicateScalar attributeValue lowerValue)
        (canonicalizePredicateScalar attributeValue upperValue)

canonicalizePredicateScalar :: Attribute -> FilterValue -> FilterValue
canonicalizePredicateScalar attributeValue filterValue =
  case filterValue of
    FilterText textValue -> FilterText (canonicalizeTextValue attributeValue textValue)
    FilterInt _ -> filterValue
    FilterDouble _ -> filterValue

planRowPredicateTree :: ResolvedRowPredicateTree -> Predicate
planRowPredicateTree predicateTree =
  case predicateTree of
    ResolvedRowPredicateLeafNode predicateLeaf ->
      PredicateLeaf
        PredicateField
          { predicateFieldTargetObject = rowPredicateTargetObjectName predicateLeaf
          , predicateFieldAttribute = rowPredicateLabel predicateLeaf
          , predicateLocation = PredicateRowField
          }
        (rowPredicateOperator predicateLeaf)
        (rowPredicateValue predicateLeaf)
    ResolvedRowPredicateAnd predicateValues ->
      PredicateAnd (map planRowPredicateTree predicateValues)
    ResolvedRowPredicateOr predicateValues ->
      PredicateOr (map planRowPredicateTree predicateValues)
    ResolvedRowPredicateNot predicateValue ->
      PredicateNot (planRowPredicateTree predicateValue)
