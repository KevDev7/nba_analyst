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

import Data.Aeson (FromJSON (parseJSON), ToJSON, withText)
import Data.Text (Text)
import GHC.Generics (Generic)

data AttributeKind
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
  { name :: Text
  , kind :: AttributeKind
  , source_column :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data MetricDef = MetricDef
  { name :: Text
  , aggregation :: Text
  , source_attributes :: [Text]
  , expression :: Text
  , executable :: Bool
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data LinkRelation
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
  { name :: Text
  , backing_table :: Text
  , description :: Text
  , attributes :: [Attribute]
  , metrics :: [MetricDef]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data Link = Link
  { source_object :: Text
  , target_object :: Text
  , relation_type :: LinkRelation
  , source_key :: Text
  , target_key :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data Ontology = Ontology
  { objects :: [Object]
  , links :: [Link]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)
