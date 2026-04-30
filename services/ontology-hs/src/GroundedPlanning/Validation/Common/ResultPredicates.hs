{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.ResultPredicates
  ( validateResultPredicateTree
  ) where

import Data.Text (Text)
import GroundedPlanning.Validation.Common.PredicateRules
import OntologyLayer.Types (AttributeKind (Measure), AttributeVisibility (Public), MetricDef (executable, name, source_attributes), Object)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validateResultPredicateTree :: Object -> OT.MetricDef -> Predicate -> Either Text ()
validateResultPredicateTree factObject selectedMetric predicateTree =
  validatePredicateTree "Result" (validateResultPredicateLeaf factObject selectedMetric) predicateTree

validateResultPredicateLeaf :: Object -> OT.MetricDef -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ()
validateResultPredicateLeaf factObject selectedMetric fieldValue operatorValue predicateValue = do
  validatePredicateLocation "Result" PredicateResultField fieldValue
  if predicateFieldTargetObject fieldValue == "" || predicateFieldTargetObject fieldValue == objectName factObject
    then pure ()
    else Left "Result predicate fields must reference the selected fact object or omit targetObject."
  validateResultPredicateField factObject selectedMetric (predicateFieldAttribute fieldValue)
  validateNumericPredicateOperatorValue
    "Result predicate tree operator/value must be numeric and valid for grouped result fields."
    operatorValue
    predicateValue

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

objectName :: Object -> Text
objectName OT.Object {OT.name = nameValue} =
  nameValue

attributeName :: OT.Attribute -> Text
attributeName OT.Attribute {OT.name = nameValue} =
  nameValue
