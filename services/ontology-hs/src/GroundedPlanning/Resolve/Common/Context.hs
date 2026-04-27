{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Context
  ( resolveContextSelection
  ) where

import Data.Text (Text)
import GroundedPlanning.Resolve.Common.Dimensions (firstLinkedObjectWithAttribute)
import GroundedPlanning.Resolve.Common.Ontology (hasAttribute, objectName)
import GroundedPlanning.Resolve.Common.Types
import OntologyLayer.Types (Ontology)
import qualified OntologyLayer.Types as OT

resolveContextSelection :: Ontology -> Text -> OT.Object -> Either Text ContextSelection
resolveContextSelection ontology factObjectName rowObject
  -- Temporary heuristic. This context selection prefers the first convenient
  -- team_abbreviation surface rather than modeling context selection as a more
  -- general semantic decision.
  | hasAttribute rowObject "team_abbreviation" =
      Right
        ContextSelection
          { selectedContextPath = Nothing
          , selectedContextColumn = Just (ColumnRef "row" "team_abbreviation")
          }
  | otherwise =
      case firstLinkedObjectWithAttribute ontology factObjectName "team_abbreviation" [objectName rowObject] of
        Just (_contextObject, discoveredContextPath) ->
          Right
            ContextSelection
              { selectedContextPath = Just discoveredContextPath
              , selectedContextColumn = Just (ColumnRef "context" "team_abbreviation")
              }
        Nothing ->
          Right
            ContextSelection
              { selectedContextPath = Nothing
              , selectedContextColumn = Nothing
              }
