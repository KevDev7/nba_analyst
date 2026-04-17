-- Purpose:
-- Provide ontology lookup helpers for live grounding and validation.
--
-- Uses:
-- - typed ontology values from Types.hs
--
-- Produces:
-- - object, attribute, and metric lookup functions
--
-- Next:
-- - QueryModel/Match.hs or GroundedPlanning/Validation.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}

module OntologyLayer.Graph where

import Data.Aeson (FromJSON, ToJSON)
import Data.List (find)
import Data.Text (Text)
import GHC.Generics (Generic)
import OntologyLayer.Types

data PathStep = PathStep
  { linkName :: Text
  , stepSourceObjectName :: Text
  , stepTargetObjectName :: Text
  , stepSourceTableName :: Text
  , stepTargetTableName :: Text
  , sourceKey :: Text
  , targetKey :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data DiscoveredPath = DiscoveredPath
  { sourceObjectName :: Text
  , targetObjectName :: Text
  , steps :: [PathStep]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

findObject :: Ontology -> Text -> Maybe Object
findObject ontology objectName = find matchesObject (objects ontology)
  where
    matchesObject Object {name = currentName} = currentName == objectName

findAttribute :: Object -> Text -> Maybe Attribute
findAttribute object attributeName = find matchesAttribute (attributes object)
  where
    matchesAttribute Attribute {name = currentName} = currentName == attributeName

findMetric :: Object -> Text -> Maybe MetricDef
findMetric object metricName = find matchesMetric (metrics object)
  where
    matchesMetric MetricDef {name = currentName} = currentName == metricName

findLink :: Ontology -> Text -> Text -> Maybe Link
findLink ontology sourceName targetName = find matchesLink (links ontology)
  where
    matchesLink Link {source_object = currentSource, target_object = currentTarget} =
      currentSource == sourceName && currentTarget == targetName

findLinkByName :: Ontology -> Text -> Maybe Link
findLinkByName ontology linkName = find matchesLinkName (links ontology)
  where
    matchesLinkName Link {name = currentName} = currentName == linkName

findLinksFrom :: Ontology -> Text -> [Link]
findLinksFrom ontology sourceName =
  filter matchesLink (links ontology)
  where
    matchesLink Link {source_object = currentSource} = currentSource == sourceName

findPath :: Ontology -> Int -> Text -> Text -> Maybe DiscoveredPath
findPath ontology maxDepth sourceName targetName
  | sourceName == targetName =
      Just
        DiscoveredPath
          { sourceObjectName = sourceName
          , targetObjectName = targetName
          , steps = []
          }
  | otherwise = find matchesTarget (findPathsFrom ontology maxDepth sourceName)
  where
    matchesTarget path = targetObjectName path == targetName

findPathsFrom :: Ontology -> Int -> Text -> [DiscoveredPath]
findPathsFrom ontology maxDepth sourceName =
  bfs [(sourceName, [])] [sourceName] []
  where
    bfs :: [(Text, [PathStep])] -> [Text] -> [DiscoveredPath] -> [DiscoveredPath]
    bfs [] _ discovered = discovered
    bfs ((currentObjectName, currentSteps) : remaining) visited discovered =
      let currentDepth = length currentSteps
          currentDiscovered =
            case currentSteps of
              [] -> discovered
              _ ->
                discovered
                  ++ [ DiscoveredPath
                        { sourceObjectName = sourceName
                        , targetObjectName = currentObjectName
                        , steps = currentSteps
                        }
                     ]
          nextExpansions =
            if currentDepth >= maxDepth
              then []
              else buildNextExpansions currentObjectName currentSteps visited
          nextQueue = remaining ++ map (\(nextObjectName, nextSteps, _) -> (nextObjectName, nextSteps)) nextExpansions
          nextVisited = visited ++ map (\(_, _, nextObjectName) -> nextObjectName) nextExpansions
       in bfs nextQueue nextVisited currentDiscovered

    buildNextExpansions :: Text -> [PathStep] -> [Text] -> [(Text, [PathStep], Text)]
    buildNextExpansions currentObjectName currentSteps visited =
      [ (target_object linkValue, currentSteps ++ [pathStep], target_object linkValue)
      | linkValue <- findLinksFrom ontology currentObjectName
      , target_object linkValue `notElem` visited
      , Just pathStep <- [buildPathStep currentObjectName linkValue]
      ]

    buildPathStep :: Text -> Link -> Maybe PathStep
    buildPathStep currentObjectName Link {name = currentName, target_object = currentTarget, source_key = currentSourceKey, target_key = currentTargetKey} = do
      sourceObject <- findObject ontology currentObjectName
      targetObject <- findObject ontology currentTarget
      pure
        PathStep
          { linkName = currentName
          , stepSourceObjectName = currentObjectName
          , stepTargetObjectName = currentTarget
          , stepSourceTableName = backing_table sourceObject
          , stepTargetTableName = backing_table targetObject
          , sourceKey = currentSourceKey
          , targetKey = currentTargetKey
          }
