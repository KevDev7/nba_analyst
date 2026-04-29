{-# LANGUAGE DuplicateRecordFields #-}

module QueryModel.SemanticDraft.MatchAccessors
  ( attributeKind
  , attributeName
  , attributeVisibility
  , metricAggregation
  , metricExecutable
  , metricName
  , metricSourceAttributes
  , objectAttributes
  , objectMetrics
  , objectName
  ) where

import Data.Text (Text)
import OntologyLayer.Types

attributeKind :: Attribute -> AttributeKind
attributeKind = kind

attributeName :: Attribute -> Text
attributeName Attribute {name = value} = value

attributeVisibility :: Attribute -> AttributeVisibility
attributeVisibility = visibility

objectAttributes :: Object -> [Attribute]
objectAttributes = attributes

objectName :: Object -> Text
objectName Object {name = value} = value

objectMetrics :: Object -> [MetricDef]
objectMetrics = metrics

metricName :: MetricDef -> Text
metricName MetricDef {name = value} = value

metricAggregation :: MetricDef -> Text
metricAggregation = aggregation

metricSourceAttributes :: MetricDef -> [Text]
metricSourceAttributes = source_attributes

metricExecutable :: MetricDef -> Bool
metricExecutable = executable
