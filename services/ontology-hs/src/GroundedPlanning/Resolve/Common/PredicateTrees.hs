{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.PredicateTrees
  ( canonicalizePredicateTreeValue
  , resolvePredicateTree
  ) where

import Data.Text (Text)
import OntologyLayer.Types (Attribute)
import GroundedPlanning.Resolve.Common.ValueCanonicalization
import QueryModel.IR

resolvePredicateTree ::
  (PredicateField -> PredicateOperator -> PredicateValue -> Either Text leaf) ->
  (leaf -> tree) ->
  ([tree] -> tree) ->
  ([tree] -> tree) ->
  (tree -> tree) ->
  Predicate ->
  Either Text tree
resolvePredicateTree resolveLeaf leafNode andNode orNode notNode predicateTree =
  case predicateTree of
    PredicateLeaf fieldValue operatorValue predicateValue ->
      leafNode <$> resolveLeaf fieldValue operatorValue predicateValue
    PredicateAnd predicateValues ->
      andNode <$> mapM nestedResolve predicateValues
    PredicateOr predicateValues ->
      orNode <$> mapM nestedResolve predicateValues
    PredicateNot predicateValue ->
      notNode <$> nestedResolve predicateValue
  where
    nestedResolve =
      resolvePredicateTree resolveLeaf leafNode andNode orNode notNode

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
