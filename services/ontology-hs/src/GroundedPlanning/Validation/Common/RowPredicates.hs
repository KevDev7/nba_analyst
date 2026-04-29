{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.RowPredicates
  ( validateRowPredicateTree
  ) where

import Data.Text (Text)
import GroundedPlanning.Validation.Common.Ontology
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (AttributeKind (Dimension, Measure, PrimaryKey), AttributeVisibility (Public), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validateRowPredicateTree :: Ontology -> Text -> Predicate -> Either Text ()
validateRowPredicateTree ontology factObjectName predicateTree =
  case predicateTree of
    PredicateLeaf fieldValue operatorValue predicateValue ->
      validateRowPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue
    PredicateAnd predicateValues -> validatePredicateChildren "AND" ontology factObjectName predicateValues
    PredicateOr predicateValues -> validatePredicateChildren "OR" ontology factObjectName predicateValues
    PredicateNot predicateValue -> validateRowPredicateTree ontology factObjectName predicateValue

validatePredicateChildren :: Text -> Ontology -> Text -> [Predicate] -> Either Text ()
validatePredicateChildren label ontology factObjectName predicateValues =
  case predicateValues of
    [] -> Left ("Row " <> label <> " predicate requires at least one child predicate.")
    _ -> mapM_ (validateRowPredicateTree ontology factObjectName) predicateValues

validateRowPredicateLeaf :: Ontology -> Text -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ()
validateRowPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue = do
  case predicateLocation fieldValue of
    PredicateRowField -> pure ()
    PredicateResultField -> Left "Row predicate trees only support row-level predicate fields."
  predicateObject <- requireObject ontology (predicateFieldTargetObject fieldValue)
  _ <- requirePath ontology factObjectName (predicateFieldTargetObject fieldValue)
  attributeValue <-
    maybe
      (Left ("Row predicate attribute '" <> predicateFieldAttribute fieldValue <> "' not found in ontology."))
      Right
      (findAttribute predicateObject (predicateFieldAttribute fieldValue))
  if OT.kind attributeValue == PrimaryKey || OT.visibility attributeValue /= Public
    then Left "Row predicate trees must reference public non-primary ontology attributes."
    else validateRowPredicateOperatorValue attributeValue operatorValue predicateValue

validateRowPredicateOperatorValue :: OT.Attribute -> PredicateOperator -> PredicateValue -> Either Text ()
validateRowPredicateOperatorValue attributeValue operatorValue predicateValue =
  case (OT.kind attributeValue, operatorValue, predicateValue) of
    (Dimension, PredicateEquals, PredicateScalar (FilterText textValue))
      | textValue /= "" -> pure ()
    (Dimension, PredicateNotEquals, PredicateScalar (FilterText textValue))
      | textValue /= "" -> pure ()
    (Dimension, PredicateIn, PredicateList values)
      | all isNonEmptyText values && not (null values) -> pure ()
    (Dimension, PredicateNotIn, PredicateList values)
      | all isNonEmptyText values && not (null values) -> pure ()
    (Dimension, PredicateContains, PredicateScalar (FilterText textValue))
      | textValue /= "" -> pure ()
    (Measure, PredicateEquals, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateNotEquals, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateGreaterThan, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateGreaterThanOrEqual, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateLessThan, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateLessThanOrEqual, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateIn, PredicateList values)
      | all isNumericFilterValue values && not (null values) -> pure ()
    (Measure, PredicateNotIn, PredicateList values)
      | all isNumericFilterValue values && not (null values) -> pure ()
    (Measure, PredicateBetween, PredicateRange lowerValue upperValue)
      | isNumericFilterValue lowerValue && isNumericFilterValue upperValue -> pure ()
    _ -> Left "Row predicate tree operator/value is not valid for the resolved ontology attribute."

isNonEmptyText :: FilterValue -> Bool
isNonEmptyText filterValue =
  case filterValue of
    FilterText textValue -> textValue /= ""
    _ -> False

isNumericFilterValue :: FilterValue -> Bool
isNumericFilterValue filterValue =
  case filterValue of
    FilterInt _ -> True
    FilterDouble _ -> True
    FilterText _ -> False
