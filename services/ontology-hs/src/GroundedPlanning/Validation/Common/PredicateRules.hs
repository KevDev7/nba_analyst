{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.PredicateRules
  ( validateNumericPredicateOperatorValue
  , validatePredicateLocation
  , validatePredicateTree
  , validateRowLikePredicateOperatorValue
  ) where

import Data.Text (Text)
import OntologyLayer.Types (AttributeKind (Dimension, Measure))
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validatePredicateTree :: Text -> (PredicateField -> PredicateOperator -> PredicateValue -> Either Text ()) -> Predicate -> Either Text ()
validatePredicateTree contextLabel validateLeaf predicateTree =
  case predicateTree of
    PredicateLeaf fieldValue operatorValue predicateValue ->
      validateLeaf fieldValue operatorValue predicateValue
    PredicateAnd predicateValues ->
      validatePredicateChildren contextLabel "AND" validateLeaf predicateValues
    PredicateOr predicateValues ->
      validatePredicateChildren contextLabel "OR" validateLeaf predicateValues
    PredicateNot predicateValue ->
      validatePredicateTree contextLabel validateLeaf predicateValue

validatePredicateChildren :: Text -> Text -> (PredicateField -> PredicateOperator -> PredicateValue -> Either Text ()) -> [Predicate] -> Either Text ()
validatePredicateChildren contextLabel logicLabel validateLeaf predicateValues =
  case predicateValues of
    [] -> Left (contextLabel <> " " <> logicLabel <> " predicate requires at least one child predicate.")
    _ -> mapM_ (validatePredicateTree contextLabel validateLeaf) predicateValues

validatePredicateLocation :: Text -> PredicateFieldLocation -> PredicateField -> Either Text ()
validatePredicateLocation contextLabel expectedLocation fieldValue =
  if predicateLocation fieldValue == expectedLocation
    then pure ()
    else Left (contextLabel <> " predicate trees only support " <> locationLabel expectedLocation <> " predicate fields.")

locationLabel :: PredicateFieldLocation -> Text
locationLabel locationValue =
  case locationValue of
    PredicateRowField -> "row-level"
    PredicateResultField -> "result-level"

validateRowLikePredicateOperatorValue :: Text -> OT.Attribute -> PredicateOperator -> PredicateValue -> Either Text ()
validateRowLikePredicateOperatorValue errorMessage attributeValue operatorValue predicateValue =
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
    _ -> Left errorMessage

validateNumericPredicateOperatorValue :: Text -> PredicateOperator -> PredicateValue -> Either Text ()
validateNumericPredicateOperatorValue errorMessage operatorValue predicateValue =
  case (operatorValue, predicateValue) of
    (PredicateEquals, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (PredicateNotEquals, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (PredicateGreaterThan, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (PredicateGreaterThanOrEqual, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (PredicateLessThan, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (PredicateLessThanOrEqual, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (PredicateIn, PredicateList values)
      | all isNumericFilterValue values && not (null values) -> pure ()
    (PredicateNotIn, PredicateList values)
      | all isNumericFilterValue values && not (null values) -> pure ()
    (PredicateBetween, PredicateRange lowerValue upperValue)
      | isNumericFilterValue lowerValue && isNumericFilterValue upperValue -> pure ()
    _ -> Left errorMessage

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
