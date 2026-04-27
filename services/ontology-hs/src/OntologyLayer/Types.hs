-- Purpose:
-- Define ontology ADTs for the live semantic-layer slices.
--
-- Uses:
-- - ontology fixture data loaded from YAML
--
-- Produces:
-- - typed ontology structures used by query-model and planning modules
--
-- Next:
-- - Load.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module OntologyLayer.Types where

import Data.Aeson ((.:), (.:?), (.!=), FromJSON (parseJSON), ToJSON, withObject, withText)
import Data.Text (Text)
import GHC.Generics (Generic)

data AttributeKind
  -- The three roles an ontology attribute can play.
  -- primary_key identifies rows, dimension groups/filters/labels data,
  -- and measure is a numeric value used by metrics.
  = PrimaryKey
  | Dimension
  | Measure
  deriving (Show, Eq, Generic, ToJSON)

instance FromJSON AttributeKind where
  parseJSON = withText "AttributeKind" $ \value ->
    case value of
      "primary_key" -> pure PrimaryKey
      "dimension" -> pure Dimension
      "measure" -> pure Measure
      _ -> fail ("Unknown attribute kind: " <> show value)

data Attribute = Attribute
  -- One field on an ontology object.
  -- This maps a semantic attribute name to a real source column and classifies
  -- how the planner is allowed to use it.
  { name :: Text
  , kind :: AttributeKind
  , source_column :: Text
  , link_key :: Bool
  , visibility :: AttributeVisibility
  , comparison_identity :: Bool
  , derivation :: Maybe AttributeDerivation
  }
  deriving (Show, Eq, Generic, ToJSON)

instance FromJSON Attribute where
  parseJSON = withObject "Attribute" $ \obj ->
    Attribute
      <$> obj .: "name"
      <*> obj .: "kind"
      <*> obj .: "source_column"
      <*> obj .: "link_key"
      <*> obj .: "visibility"
      <*> obj .:? "comparison_identity" .!= False
      <*> obj .: "derivation"

data AttributeDerivation = AttributeDerivation
  -- A derived attribute computed from another attribute.
  -- Example: game_year_month is derived from game_date with a SQL expression.
  { source_attribute :: Text
  , sql_expression :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data AttributeVisibility
  -- Public attributes can be used for user-facing grouping/display/filtering.
  -- Internal attributes are available to the system but should not be surfaced directly.
  = Public
  | Internal
  deriving (Show, Eq, Generic, ToJSON)

instance FromJSON AttributeVisibility where
  parseJSON = withText "AttributeVisibility" $ \value ->
    case value of
      "public" -> pure Public
      "internal" -> pure Internal
      _ -> fail ("Unknown attribute visibility: " <> show value)

data MetricDef = MetricDef
  -- A named calculation defined on one object.
  -- source_attributes must refer to attributes on the same object; the metric
  -- name itself does not need to be a physical database column.
  { name :: Text
  , aggregation :: Text
  , source_attributes :: [Text]
  , expression :: Text
  , executable :: Bool
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data LinkRelation
  -- Cardinality metadata for relationships between ontology objects.
  = OneToOne
  | OneToMany
  | ManyToOne
  | ManyToMany
  deriving (Show, Eq, Generic, ToJSON)

instance FromJSON LinkRelation where
  parseJSON = withText "LinkRelation" $ \value ->
    case value of
      "one_to_one" -> pure OneToOne
      "one_to_many" -> pure OneToMany
      "many_to_one" -> pure ManyToOne
      "many_to_many" -> pure ManyToMany
      _ -> fail ("Unknown link relation: " <> show value)

data Object = Object
  -- A business-facing wrapper around one backing SQL table.
  -- It owns attributes and metrics that the planner can ground queries against.
  { name :: Text
  , backing_table :: Text
  , description :: Text
  , attributes :: [Attribute]
  , metrics :: [MetricDef]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data Link = Link
  -- A relationship between two ontology objects.
  -- The graph/path helpers use these links to discover safe join paths.
  { name :: Text
  , source_object :: Text
  , target_object :: Text
  , relation_type :: LinkRelation
  , source_key :: Text
  , target_key :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data Ontology = Ontology
  -- The full semantic model after semantic-gold.yaml is decoded.
  -- Objects describe business entities/facts; links describe how they connect.
  { objects :: [Object]
  , links :: [Link]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)
