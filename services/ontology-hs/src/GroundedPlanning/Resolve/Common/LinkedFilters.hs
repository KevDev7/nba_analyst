{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.LinkedFilters
  ( resolveLinkedFilter
  ) where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common.Ontology
import GroundedPlanning.Resolve.Common.Types
import GroundedPlanning.Resolve.Common.ValueCanonicalization
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (Ontology)
import QueryModel.IR

resolveLinkedFilter :: Ontology -> Text -> LinkedFilter -> Either Text ResolvedLinkedFilter
resolveLinkedFilter ontology factObjectName linkedFilterValue = do
  discoveredFilterPath <- requirePath ontology factObjectName (targetObject linkedFilterValue)
  targetObjectValue <- requireObject ontology (targetObject linkedFilterValue)
  _ <- maybe
    (Left ("Could not resolve linked filter attribute '" <> attribute linkedFilterValue <> "' against the ontology."))
    Right
    (findAttribute targetObjectValue (attribute linkedFilterValue))
  pure
    ResolvedLinkedFilter
      { targetObjectName = targetObject linkedFilterValue
      , filterPath = discoveredFilterPath
      , filterColumn = attribute linkedFilterValue
      , filterValue = canonicalizeTextValue (targetObject linkedFilterValue) (attribute linkedFilterValue) rawFilterValue
      }
  where
    rawFilterValue =
      case linkedFilterValue of
        LinkedFilter {value = filterTextValue'} -> filterTextValue'
