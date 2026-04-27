{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Ontology
  ( hasAttribute
  , objectName
  , requireMetric
  , requireObject
  , requirePath
  ) where

import Data.Text (Text)
import OntologyLayer.Graph (DiscoveredPath, findAttribute, findMetric, findObject, findPath)
import OntologyLayer.Types (MetricDef, Ontology)
import qualified OntologyLayer.Types as OT

hasAttribute :: OT.Object -> Text -> Bool
hasAttribute objectValue attributeName =
  case findAttribute objectValue attributeName of
    Just _ -> True
    Nothing -> False

requireObject :: Ontology -> Text -> Either Text OT.Object
requireObject ontology objectNameValue =
  maybe (Left ("Could not resolve object '" <> objectNameValue <> "' against the ontology.")) Right $
    findObject ontology objectNameValue

requireMetric :: OT.Object -> Text -> Either Text MetricDef
requireMetric objectValue metricNameValue =
  maybe (Left ("Could not resolve metric '" <> metricNameValue <> "' against the ontology.")) Right $
    findMetric objectValue metricNameValue

requirePath :: Ontology -> Text -> Text -> Either Text DiscoveredPath
requirePath ontology sourceName targetName =
  maybe
    (Left ("Could not resolve an ontology path from '" <> sourceName <> "' to '" <> targetName <> "'."))
    Right
    (findPath ontology 2 sourceName targetName)

objectName :: OT.Object -> Text
objectName objectValue =
  case objectValue of
    OT.Object {OT.name = currentName} -> currentName
