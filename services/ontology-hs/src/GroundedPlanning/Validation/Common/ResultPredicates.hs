{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.ResultPredicates
  ( validateResultPredicateTree
  ) where

import Data.Text (Text)
import OntologyLayer.Types (AttributeKind (Measure), AttributeVisibility (Public), MetricDef (executable, name, source_attributes), Object)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validateResultPredicateTree :: Object -> OT.MetricDef -> Predicate -> Either Text ()
validateResultPredicateTree factObject selectedMetric predicateTree =
  case predicateTree of
    PredicateLeaf fieldValue operatorValue predicateValue ->
      validateResultPredicateLeaf factObject selectedMetric fieldValue operatorValue predicateValue
    PredicateAnd predicateValues -> validatePredicateChildren "AND" factObject selectedMetric predicateValues
    PredicateOr predicateValues -> validatePredicateChildren "OR" factObject selectedMetric predicateValues
    PredicateNot predicateValue -> validateResultPredicateTree factObject selectedMetric predicateValue

validatePredicateChildren :: Text -> Object -> OT.MetricDef -> [Predicate] -> Either Text ()
validatePredicateChildren label factObject selectedMetric predicateValues =
  case predicateValues of
    [] -> Left ("Result " <> label <> " predicate requires at least one child predicate.")
    _ -> mapM_ (validateResultPredicateTree factObject selectedMetric) predicateValues

validateResultPredicateLeaf :: Object -> OT.MetricDef -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ()
validateResultPredicateLeaf factObject selectedMetric fieldValue operatorValue predicateValue = do
  case predicateLocation fieldValue of
    PredicateResultField -> pure ()
    PredicateRowField -> Left "Result predicate trees only support result-level predicate fields."
  if predicateFieldTargetObject fieldValue == "" || predicateFieldTargetObject fieldValue == objectName factObject
    then pure ()
    else Left "Result predicate fields must reference the selected fact object or omit targetObject."
  validateResultPredicateField factObject selectedMetric (predicateFieldAttribute fieldValue)
  validateResultPredicateOperatorValue operatorValue predicateValue

validateResultPredicateField :: Object -> OT.MetricDef -> Text -> Either Text ()
validateResultPredicateField factObject selectedMetric attributeValue
  | attributeValue == "metric_value" || attributeValue == name selectedMetric = pure ()
  | otherwise =
      case matchingMetrics of
        _ : _ -> pure ()
        [] ->
          case matchingPublicMeasureAttributes of
            _ : _ -> pure ()
            [] -> Left ("Result predicate field '" <> attributeValue <> "' could not be grounded to a result metric or public measure.")
  where
    matchingMetrics =
      [ metricValue
      | metricValue <- OT.metrics factObject
      , executable metricValue
      , name metricValue == attributeValue
      , length (source_attributes metricValue) == 1
      ]
    matchingPublicMeasureAttributes =
      [ attribute
      | attribute <- OT.attributes factObject
      , attributeName attribute == attributeValue
      , OT.kind attribute == Measure
      , OT.visibility attribute == Public
      ]

validateResultPredicateOperatorValue :: PredicateOperator -> PredicateValue -> Either Text ()
validateResultPredicateOperatorValue operatorValue predicateValue =
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
    _ -> Left "Result predicate tree operator/value must be numeric and valid for grouped result fields."

isNumericFilterValue :: FilterValue -> Bool
isNumericFilterValue filterValue =
  case filterValue of
    FilterInt _ -> True
    FilterDouble _ -> True
    FilterText _ -> False

objectName :: Object -> Text
objectName OT.Object {OT.name = nameValue} =
  nameValue

attributeName :: OT.Attribute -> Text
attributeName OT.Attribute {OT.name = nameValue} =
  nameValue
