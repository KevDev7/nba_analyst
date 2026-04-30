{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.Find.Role
  ( RoleIdentityMatch (..)
  , resolveRoleIdentityMatch
  , roleFieldScore
  ) where

import Data.List (sortOn)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (DiscoveredPath (steps), findAllPathsFrom, findAttribute, findObject)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (AttributeKind (Dimension), AttributeVisibility (Public), Object, Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.SemanticConstruction.Match (attributeName, identityDimension, objectName)
import QueryModel.SemanticDraft.Normalize (normalizedKey, normalizedMeasureKey)

data RoleIdentityMatch = RoleIdentityMatch
  { roleIdentityObject :: Object
  , roleIdentityAttribute :: OT.Attribute
  , roleIdentityLinkRole :: Text
  , roleIdentityLabel :: Text
  }

resolveRoleIdentityMatch :: Ontology -> Object -> Text -> Maybe RoleIdentityMatch
resolveRoleIdentityMatch ontology factObjectValue rawField =
  case sortOn roleIdentityRank roleIdentityCandidates of
    (_, candidate) : _ -> Just candidate
    [] -> Nothing
  where
    roleIdentityCandidates =
      [ ( scoreValue
        , RoleIdentityMatch
            { roleIdentityObject = linkedObject
            , roleIdentityAttribute = identityAttribute
            , roleIdentityLinkRole = lastLinkName pathValue
            , roleIdentityLabel = roleFieldLabel rawField pathValue linkedObject (attributeName identityAttribute)
            }
        )
      | pathValue <- findAllPathsFrom ontology 2 (objectName factObjectValue)
      , Just linkedObject <- [findObject ontology (OG.targetObjectName pathValue)]
      , Just identityName <- [roleIdentityDimension linkedObject]
      , Just identityAttribute <- [findAttribute linkedObject identityName]
      , isPublicRoleIdentityAttribute identityAttribute
      , let scoreValue = roleFieldScore rawField pathValue linkedObject identityName
      , scoreValue > 0
      ]
    roleIdentityRank (scoreValue, candidate) =
      ( Down scoreValue
      , roleIdentityLinkRole candidate
      , objectName (roleIdentityObject candidate)
      , attributeName (roleIdentityAttribute candidate)
      )

lastLinkName :: DiscoveredPath -> Text
lastLinkName pathValue =
  case reverse (steps pathValue) of
    stepValue : _ -> OG.linkName stepValue
    [] -> ""

roleIdentityDimension :: Object -> Maybe Text
roleIdentityDimension objectValue = do
  identityName <- identityDimension objectValue
  if "name" `T.isInfixOf` normalizedKey identityName
    then Just identityName
    else Nothing

isPublicRoleIdentityAttribute :: OT.Attribute -> Bool
isPublicRoleIdentityAttribute attributeValue =
  OT.visibility attributeValue == Public
    && OT.kind attributeValue == Dimension

roleFieldScore :: Text -> DiscoveredPath -> Object -> Text -> Int
roleFieldScore rawField pathValue linkedObject identityName =
  maximum (0 : [score | (aliasValue, score) <- roleFieldAliases pathValue linkedObject identityName, aliasValue == rawKey])
  where
    rawKey = normalizedMeasureKey rawField

roleFieldAliases :: DiscoveredPath -> Object -> Text -> [(Text, Int)]
roleFieldAliases pathValue linkedObject identityName =
  [ (roleKey, 110)
  , (roleKey <> targetKey, 105)
  , (roleKey <> targetKey <> "name", 100)
  , (roleKey <> "name", 95)
  , (roleKey <> identityKey, 90)
  ]
    <> sourceKeyAliases
    <> linkNameAliases
  where
    targetKey = normalizedKey (objectName linkedObject)
    identityKey = normalizedMeasureKey identityName
    roleKey = normalizedRoleKey pathValue linkedObject
    sourceKeyAliases =
      concat
        [ [ (T.replace "id" "" sourceKeyValue, 85)
          , (T.replace targetKey "" (T.replace "id" "" sourceKeyValue), 90)
          ]
        | stepValue <- maybeLastStep pathValue
        , let sourceKeyValue = normalizedMeasureKey (OG.sourceKey stepValue)
        ]
    linkNameAliases =
      concat
        [ [ (linkNameValue, 80)
          , (T.replace targetKey "" linkNameValue, 85)
          ]
        | stepValue <- maybeLastStep pathValue
        , let linkNameValue = normalizedMeasureKey (OG.linkName stepValue)
        ]

normalizedRoleKey :: DiscoveredPath -> Object -> Text
normalizedRoleKey pathValue linkedObject =
  case maybeLastStep pathValue of
    stepValue : _ ->
      let targetKey = normalizedKey (objectName linkedObject)
          sourceObjectKey = normalizedKey (OG.stepSourceObjectName stepValue)
          linkKey = normalizedMeasureKey (OG.linkName stepValue)
          sourceKeyValue = normalizedMeasureKey (OG.sourceKey stepValue)
          fromLink = T.replace targetKey "" (T.replace sourceObjectKey "" linkKey)
          fromSourceKey = T.replace "id" "" (T.replace targetKey "" sourceKeyValue)
       in if fromLink /= "" then fromLink else fromSourceKey
    [] -> ""

maybeLastStep :: DiscoveredPath -> [OG.PathStep]
maybeLastStep pathValue =
  case reverse (steps pathValue) of
    stepValue : _ -> [stepValue]
    [] -> []

roleFieldLabel :: Text -> DiscoveredPath -> Object -> Text -> Text
roleFieldLabel _rawField pathValue linkedObject identityName =
  case normalizedRoleKey pathValue linkedObject of
    "" -> identityName
    roleKey -> roleKey
