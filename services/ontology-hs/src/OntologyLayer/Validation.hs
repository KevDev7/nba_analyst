-- Purpose:
-- Validate ontology integrity before query modeling or planning uses it.
--
-- Uses:
-- - typed ontology values from Types.hs
--
-- Produces:
-- - a load-time validation decision for the semantic contract
--
-- Next:
-- - Load.hs

{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module OntologyLayer.Validation where

import Data.List (group, sort)
import Data.Maybe (mapMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (findAttribute, findObject)
import OntologyLayer.Types
  ( Attribute (comparison_identity, kind, link_key)
  , AttributeDerivation (source_attribute)
  , AttributeKind (Dimension, PrimaryKey)
  , AttributeVisibility (Public)
  , Link (source_key, source_object, target_key, target_object)
  , MetricDef (expression, source_attributes)
  , Object (attributes, metrics)
  , Ontology (links, objects)
  )
import qualified OntologyLayer.Types as OT

validateOntology :: Ontology -> Either Text ()
validateOntology ontology =
  -- Run every ontology integrity check before query modeling/planning can use it.
  case validationErrors ontology of
    [] -> Right ()
    errors ->
      Left $
        T.unlines
          ( "Invalid ontology:"
              : map ("- " <>) errors
          )

validationErrors :: Ontology -> [Text]
validationErrors ontology =
  -- Gather all validation errors at once so the YAML author gets a useful list.
  duplicateObjectErrors ontology
    ++ duplicateLinkErrors ontology
    ++ concatMap validateObject (objects ontology)
    ++ concatMap (validateLink ontology) (links ontology)

duplicateObjectErrors :: Ontology -> [Text]
duplicateObjectErrors ontology =
  -- Object names are semantic IDs, so duplicates would make grounding ambiguous.
  [ "Duplicate object name '" <> objectNameValue <> "'."
  | objectNameValue <- duplicates [objectName objectValue | objectValue <- objects ontology]
  ]

duplicateLinkErrors :: Ontology -> [Text]
duplicateLinkErrors ontology =
  -- Link names are used in discovered paths/debug output, so they must be unique.
  [ "Duplicate link name '" <> linkNameValue <> "'."
  | linkNameValue <- duplicates [linkName linkValue | linkValue <- links ontology]
  ]

validateObject :: Object -> [Text]
validateObject objectValue =
  -- Check one object: its fields, metrics, and required identity shape.
  duplicateAttributeErrors objectValue
    ++ duplicateMetricErrors objectValue
    ++ primaryKeyErrors objectValue
    ++ concatMap (validateAttribute objectValue) (attributes objectValue)
    ++ concatMap (validateMetric objectValue) (metrics objectValue)

duplicateAttributeErrors :: Object -> [Text]
duplicateAttributeErrors objectValue =
  -- Attribute names must be unique inside an object so lookup by name is safe.
  [ "Object '" <> objectName objectValue <> "' has duplicate attribute '" <> attributeNameValue <> "'."
  | attributeNameValue <- duplicates [attributeName attributeValue | attributeValue <- attributes objectValue]
  ]

duplicateMetricErrors :: Object -> [Text]
duplicateMetricErrors objectValue =
  -- Metric names must be unique inside an object so query grounding is unambiguous.
  [ "Object '" <> objectName objectValue <> "' has duplicate metric '" <> metricNameValue <> "'."
  | metricNameValue <- duplicates [metricName metricValue | metricValue <- metrics objectValue]
  ]

primaryKeyErrors :: Object -> [Text]
primaryKeyErrors objectValue =
  -- Every object needs at least one primary key so links and row identity work.
  if null primaryKeys
    then ["Object '" <> objectName objectValue <> "' must define at least one primary-key attribute."]
    else []
  where
    primaryKeys =
      [ attributeValue
      | attributeValue <- attributes objectValue
      , kind attributeValue == PrimaryKey
      ]

validateAttribute :: Object -> Attribute -> [Text]
validateAttribute objectValue attributeValue =
  -- Check rules that apply to one attribute.
  comparisonIdentityErrors objectValue attributeValue
    ++ derivationErrors objectValue attributeValue

comparisonIdentityErrors :: Object -> Attribute -> [Text]
comparisonIdentityErrors objectValue attributeValue =
  -- If an attribute can identify entities in comparisons, it must be safe to show.
  if comparison_identity attributeValue && not isPublicDimension
    then
      [ "Object '"
          <> objectName objectValue
          <> "' marks attribute '"
          <> attributeName attributeValue
          <> "' as a comparison identity, but comparison identities must be public dimensions."
      ]
    else []
  where
    isPublicDimension =
      kind attributeValue == Dimension
        && OT.visibility attributeValue == Public

derivationErrors :: Object -> Attribute -> [Text]
derivationErrors objectValue attributeValue =
  -- Derived attributes must point to an existing source attribute on the same object.
  case OT.derivation attributeValue of
    Nothing -> []
    Just derivationValue ->
      case findAttribute objectValue (source_attribute derivationValue) of
        Just _ -> []
        Nothing ->
          [ "Object '"
              <> objectName objectValue
              <> "' has derived attribute '"
              <> attributeName attributeValue
              <> "' referencing missing source attribute '"
              <> source_attribute derivationValue
              <> "'."
          ]

validateMetric :: Object -> MetricDef -> [Text]
validateMetric objectValue metricValue =
  -- Check one metric definition before the planner can use it.
  emptyMetricExpressionErrors objectValue metricValue
    ++ metricSourceAttributeErrors objectValue metricValue

emptyMetricExpressionErrors :: Object -> MetricDef -> [Text]
emptyMetricExpressionErrors objectValue metricValue =
  -- A metric must have a calculation expression, even if execution support is limited.
  if T.null (T.strip (expression metricValue))
    then
      [ "Object '"
          <> objectName objectValue
          <> "' metric '"
          <> metricName metricValue
          <> "' must define a non-empty expression."
      ]
    else []

metricSourceAttributeErrors :: Object -> MetricDef -> [Text]
metricSourceAttributeErrors objectValue metricValue =
  -- Metric source_attributes must exist on the same object that owns the metric.
  [ "Object '"
      <> objectName objectValue
      <> "' metric '"
      <> metricName metricValue
      <> "' references missing source attribute '"
      <> sourceAttributeName
      <> "'."
  | sourceAttributeName <- source_attributes metricValue
  , findAttribute objectValue sourceAttributeName == Nothing
  ]

validateLink :: Ontology -> Link -> [Text]
validateLink ontology linkValue =
  -- Check that each relationship connects real objects through legal key fields.
  case (findObject ontology (source_object linkValue), findObject ontology (target_object linkValue)) of
    (Nothing, Nothing) ->
      [ "Link '"
          <> linkName linkValue
          <> "' references missing source object '"
          <> source_object linkValue
          <> "' and missing target object '"
          <> target_object linkValue
          <> "'."
      ]
    (Nothing, Just _) ->
      [ "Link '"
          <> linkName linkValue
          <> "' references missing source object '"
          <> source_object linkValue
          <> "'."
      ]
    (Just _, Nothing) ->
      [ "Link '"
          <> linkName linkValue
          <> "' references missing target object '"
          <> target_object linkValue
          <> "'."
      ]
    (Just sourceObject, Just targetObject) ->
      sourceKeyErrors sourceObject
        ++ targetKeyErrors targetObject
  where
    sourceKeyErrors sourceObject =
      -- The source side of a link must exist and be marked as a link_key.
      case findAttribute sourceObject (source_key linkValue) of
        Nothing ->
          [ "Link '"
              <> linkName linkValue
              <> "' source key '"
              <> source_key linkValue
              <> "' does not exist on object '"
              <> source_object linkValue
              <> "'."
          ]
        Just attributeValue ->
          if link_key attributeValue
            then []
            else
              [ "Link '"
                  <> linkName linkValue
                  <> "' source key '"
                  <> source_key linkValue
                  <> "' on object '"
                  <> source_object linkValue
                  <> "' must be marked as link_key."
              ]

    targetKeyErrors targetObject =
      -- The target side of a link must point at a primary key.
      case findAttribute targetObject (target_key linkValue) of
        Nothing ->
          [ "Link '"
              <> linkName linkValue
              <> "' target key '"
              <> target_key linkValue
              <> "' does not exist on object '"
              <> target_object linkValue
              <> "'."
          ]
        Just attributeValue ->
          if kind attributeValue == PrimaryKey
            then []
            else
              [ "Link '"
                  <> linkName linkValue
                  <> "' target key '"
                  <> target_key linkValue
                  <> "' on object '"
                  <> target_object linkValue
                  <> "' must be a primary key."
              ]

duplicates :: Ord a => [a] -> [a]
duplicates =
  -- Return each value that appears more than once.
  mapMaybe duplicatedValue . group . sort
  where
    duplicatedValue currentGroup =
      case currentGroup of
        duplicated : _ : _ -> Just duplicated
        _ -> Nothing

objectName :: Object -> Text
objectName OT.Object {OT.name = currentName} = currentName

attributeName :: Attribute -> Text
attributeName OT.Attribute {OT.name = currentName} = currentName

metricName :: MetricDef -> Text
metricName OT.MetricDef {OT.name = currentName} = currentName

linkName :: Link -> Text
linkName OT.Link {OT.name = currentName} = currentName
