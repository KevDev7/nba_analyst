{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.RowPredicates
  ( validateRowPredicateTree
  ) where

import Data.Text (Text)
import GroundedPlanning.Validation.Common.Ontology
import GroundedPlanning.Validation.Common.PredicateRules
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (AttributeKind (PrimaryKey), AttributeVisibility (Public), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validateRowPredicateTree :: Ontology -> Text -> Predicate -> Either Text ()
validateRowPredicateTree ontology factObjectName predicateTree =
  validatePredicateTree "Row" (validateRowPredicateLeaf ontology factObjectName) predicateTree

validateRowPredicateLeaf :: Ontology -> Text -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ()
validateRowPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue = do
  validatePredicateLocation "Row" PredicateRowField fieldValue
  predicateObject <- requireObject ontology (predicateFieldTargetObject fieldValue)
  _ <- requirePath ontology factObjectName (predicateFieldTargetObject fieldValue)
  attributeValue <-
    maybe
      (Left ("Row predicate attribute '" <> predicateFieldAttribute fieldValue <> "' not found in ontology."))
      Right
      (findAttribute predicateObject (predicateFieldAttribute fieldValue))
  if OT.kind attributeValue == PrimaryKey || OT.visibility attributeValue /= Public
    then Left "Row predicate trees must reference public non-primary ontology attributes."
    else
      validateRowLikePredicateOperatorValue
        "Row predicate tree operator/value is not valid for the resolved ontology attribute."
        attributeValue
        operatorValue
        predicateValue
