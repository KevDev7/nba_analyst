{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Ontology
  ( firstLinkedObjectWithAttribute
  , hasAttribute
  , objectName
  , objectWithAttribute
  , requireAttributeKind
  , requireFactAttribute
  , requireMetric
  , requireObject
  , requirePath
  ) where

import Data.Text (Text)
import OntologyLayer.Graph (DiscoveredPath, findAttribute, findMetric, findObject, findPath, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (Object, Ontology)
import qualified OntologyLayer.Types as OT

firstLinkedObjectWithAttribute :: Ontology -> Text -> Text -> Maybe Object
firstLinkedObjectWithAttribute ontology factObjectName attributeName =
  case
    [ objectValue
    | discoveredPath <- findPathsFrom ontology 2 factObjectName
    , Just objectValue <- [findObject ontology (OG.targetObjectName discoveredPath)]
    , hasAttribute objectValue attributeName
    ]
    of
    objectValue : _ -> Just objectValue
    [] -> Nothing

objectWithAttribute :: Ontology -> Text -> Text -> Maybe Object
objectWithAttribute ontology objectNameValue attributeName = do
  objectValue <- findObject ontology objectNameValue
  if hasAttribute objectValue attributeName
    then Just objectValue
    else Nothing

hasAttribute :: Object -> Text -> Bool
hasAttribute objectValue attributeName =
  case findAttribute objectValue attributeName of
    Just _ -> True
    Nothing -> False

requireObject :: Ontology -> Text -> Either Text Object
requireObject ontology objectNameValue =
  maybe (Left ("Object '" <> objectNameValue <> "' not found in ontology.")) Right $
    findObject ontology objectNameValue

requirePath :: Ontology -> Text -> Text -> Either Text DiscoveredPath
requirePath ontology sourceName targetName =
  maybe
    ( Left
        ( "No valid ontology path from '"
            <> sourceName
            <> "' to '"
            <> targetName
            <> "'."
        )
    )
    Right
    (findPath ontology 2 sourceName targetName)

requireMetric :: Object -> Text -> Either Text OT.MetricDef
requireMetric object metricNameValue =
  maybe (Left ("Metric '" <> metricNameValue <> "' not found in ontology.")) Right $
    findMetric object metricNameValue

requireAttributeKind :: Object -> Text -> OT.AttributeKind -> Either Text ()
requireAttributeKind object attributeName expectedKind = do
  attribute <- maybe (Left ("Attribute '" <> attributeName <> "' not found in ontology.")) Right $
    findAttribute object attributeName
  if OT.kind attribute == expectedKind
    then pure ()
    else Left ("Attribute '" <> attributeName <> "' has the wrong kind in the ontology.")

requireFactAttribute :: Object -> Text -> Text -> Either Text ()
requireFactAttribute factObject attributeName failureMessage =
  case findAttribute factObject attributeName of
    Just _ -> pure ()
    _ -> Left failureMessage

objectName :: OT.Object -> Text
objectName objectValue =
  case objectValue of
    OT.Object {OT.name = currentName} -> currentName
