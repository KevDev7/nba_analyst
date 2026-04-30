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
  -- One hop across an ontology link.
  -- Grounded planning later turns these path steps into SQL joins.
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
  -- A discovered route from one ontology object to another.
  -- Example: PlayerGame -> Player.
  { sourceObjectName :: Text
  , targetObjectName :: Text
  , steps :: [PathStep]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

findObject :: Ontology -> Text -> Maybe Object
findObject ontology objectName = find matchesObject (objects ontology)
  -- Find a business object by its ontology name.
  where
    matchesObject Object {name = currentName} = currentName == objectName

findAttribute :: Object -> Text -> Maybe Attribute
findAttribute object attributeName = find matchesAttribute (attributes object)
  -- Find an attribute by name inside one object.
  where
    matchesAttribute Attribute {name = currentName} = currentName == attributeName

findMetric :: Object -> Text -> Maybe MetricDef
findMetric object metricName = find matchesMetric (metrics object)
  -- Find a metric by name inside one object.
  where
    matchesMetric MetricDef {name = currentName} = currentName == metricName

findLink :: Ontology -> Text -> Text -> Maybe Link
findLink ontology sourceName targetName = find matchesLink (links ontology)
  -- Find a direct relationship from one object to another.
  where
    matchesLink Link {source_object = currentSource, target_object = currentTarget} =
      currentSource == sourceName && currentTarget == targetName

findLinkByName :: Ontology -> Text -> Maybe Link
findLinkByName ontology linkName = find matchesLinkName (links ontology)
  -- Find a relationship by its configured link name.
  where
    matchesLinkName Link {name = currentName} = currentName == linkName

findLinksFrom :: Ontology -> Text -> [Link]
findLinksFrom ontology sourceName =
  -- List all outgoing links from one object.
  filter matchesLink (links ontology)
  where
    matchesLink Link {source_object = currentSource} = currentSource == sourceName

findPath :: Ontology -> Int -> Text -> Text -> Maybe DiscoveredPath
findPath ontology maxDepth sourceName targetName
  -- Find one path from source object to target object, up to maxDepth hops.
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

findPathByLastLinkName :: Ontology -> Int -> Text -> Text -> Text -> Maybe DiscoveredPath
findPathByLastLinkName ontology maxDepth sourceName targetName linkRole =
  find matchesRole (findAllPathsFrom ontology maxDepth sourceName)
  where
    matchesRole path =
      targetObjectName path == targetName
        && case reverse (steps path) of
          stepValue : _ -> linkName stepValue == linkRole
          [] -> False

findPathsFrom :: Ontology -> Int -> Text -> [DiscoveredPath]
findPathsFrom ontology maxDepth sourceName =
  -- Breadth-first search over ontology links starting from one object.
  -- This gives planners possible join paths without hardcoding table joins.
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
      -- Expand to unvisited objects reachable by one outgoing link.
      [ (target_object linkValue, currentSteps ++ [pathStep], target_object linkValue)
      | linkValue <- findLinksFrom ontology currentObjectName
      , target_object linkValue `notElem` visited
      , Just pathStep <- [buildPathStep currentObjectName linkValue]
      ]

    buildPathStep :: Text -> Link -> Maybe PathStep
    buildPathStep currentObjectName Link {name = currentName, target_object = currentTarget, source_key = currentSourceKey, target_key = currentTargetKey} = do
      -- Add table/key metadata to the link so SQL compilation has what it needs.
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

findAllPathsFrom :: Ontology -> Int -> Text -> [DiscoveredPath]
findAllPathsFrom ontology maxDepth sourceName =
  -- Like findPathsFrom, but keeps distinct relationship roles even when they
  -- point to the same target object. Example: TeamGame -> Team can mean the
  -- team or the opponent team depending on the link.
  bfs [(sourceName, [], [sourceName])] []
  where
    bfs :: [(Text, [PathStep], [Text])] -> [DiscoveredPath] -> [DiscoveredPath]
    bfs [] discovered = discovered
    bfs ((currentObjectName, currentSteps, visitedPathObjects) : remaining) discovered =
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
              else buildNextExpansions currentObjectName currentSteps visitedPathObjects
          nextQueue =
            remaining
              ++ [ (nextObjectName, nextSteps, visitedPathObjects ++ [nextObjectName])
                 | (nextObjectName, nextSteps) <- nextExpansions
                 ]
       in bfs nextQueue currentDiscovered

    buildNextExpansions :: Text -> [PathStep] -> [Text] -> [(Text, [PathStep])]
    buildNextExpansions currentObjectName currentSteps visitedPathObjects =
      [ (target_object linkValue, currentSteps ++ [pathStep])
      | linkValue <- findLinksFrom ontology currentObjectName
      , target_object linkValue `notElem` visitedPathObjects
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
