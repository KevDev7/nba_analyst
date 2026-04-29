{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.ValueCanonicalization
  ( canonicalizeTextValue
  ) where

import Data.Maybe (listToMaybe)
import qualified Data.Map.Strict as Map
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Types (Attribute (value_aliases))

canonicalizeTextValue :: Attribute -> Text -> Text
canonicalizeTextValue attributeValue rawValue =
  -- By this point grounding has already selected the exact ontology attribute.
  -- Value aliases are therefore safe to apply without phrase-specific planner
  -- corridors: the ontology contract owns the mapping.
  maybe rawValue id (lookupValueAlias attributeValue rawValue)

lookupValueAlias :: Attribute -> Text -> Maybe Text
lookupValueAlias attributeValue rawValue =
  listToMaybe
    [ canonicalValue
    | (canonicalValue, aliases) <- Map.toList (value_aliases attributeValue)
    , aliasValue <- canonicalValue : aliases
    , normalizedValue aliasValue == normalizedRawValue
    ]
  where
    normalizedRawValue = normalizedValue rawValue

normalizedValue :: Text -> Text
normalizedValue =
  T.filter isAliasCharacter . T.toLower . T.strip

isAliasCharacter :: Char -> Bool
isAliasCharacter character =
  ('a' <= character && character <= 'z') || ('0' <= character && character <= '9')
