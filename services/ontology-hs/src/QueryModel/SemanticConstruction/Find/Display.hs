{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.Find.Display
  ( resolveFindDisplayDimensions
  , resolveFindOrders
  ) where

import Control.Applicative ((<|>))
import Data.List (nub, sortOn)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (DiscoveredPath (steps), findAllPathsFrom, findAttribute, findObject)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (AttributeKind (Dimension, Measure), AttributeVisibility (Public), Object, Ontology)
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticConstruction.Find.Predicate (resolveFindPredicateAttribute)
import QueryModel.SemanticConstruction.Match
import QueryModel.SemanticDraft.Normalize
import QueryModel.SemanticDraft.Types

resolveFindDisplayDimensions :: Ontology -> Object -> [Object] -> Object -> [Text] -> Text -> Maybe [QI.FindDisplaySpec]
resolveFindDisplayDimensions ontology targetObject actorObjects factObjectValue requestedDimensions identityDimensionValue =
  case requestedDimensions of
    [] -> Just (map QI.simpleFindDisplaySpec (defaultFindDisplayDimensionsFor targetObject identityDimensionValue))
    _ ->
      nub <$> mapM (resolveFindDisplaySpec ontology targetObject actorObjects factObjectValue) requestedDimensions

defaultFindDisplayDimensionsFor :: Object -> Text -> [Text]
defaultFindDisplayDimensionsFor targetObject identityDimensionValue =
  case objectName targetObject of
    "Game" -> publicDimensionsNamed ["game_date", "season_year", "season_type"] targetObject
    _ ->
      nub $
        identityDimensionValue
          : publicDimensionsNamed
            ["game_date", "season_year", "season_type", "team_name", "team_abbreviation", "full_name"]
            targetObject

publicDimensionsNamed :: [Text] -> Object -> [Text]
publicDimensionsNamed dimensionNames objectValue =
  [ dimensionName
  | dimensionName <- dimensionNames
  , Just attributeValue <- [findAttribute objectValue dimensionName]
  , attributeKind attributeValue == Dimension
  , attributeVisibility attributeValue == Public
  ]

resolveFindDisplaySpec :: Ontology -> Object -> [Object] -> Object -> Text -> Maybe QI.FindDisplaySpec
resolveFindDisplaySpec ontology targetObject actorObjects factObjectValue rawField =
  resolveFindAttributeDisplaySpec ontology targetObject actorObjects factObjectValue rawField
    <|> resolveFindRoleDisplaySpec ontology factObjectValue rawField

resolveFindAttributeDisplaySpec :: Ontology -> Object -> [Object] -> Object -> Text -> Maybe QI.FindDisplaySpec
resolveFindAttributeDisplaySpec ontology targetObject actorObjects factObjectValue rawField = do
  (_, attributeValue) <- resolveFindPredicateAttribute ontology targetObject actorObjects factObjectValue rawField
  if isPublicFindDisplayAttribute attributeValue
    then Just (QI.simpleFindDisplaySpec (attributeName attributeValue))
    else Nothing

resolveFindRoleDisplaySpec :: Ontology -> Object -> Text -> Maybe QI.FindDisplaySpec
resolveFindRoleDisplaySpec ontology factObjectValue rawField =
  case sortOn roleDisplayRank roleDisplayCandidates of
    (_, candidate) : _ -> Just candidate
    [] -> Nothing
  where
    roleDisplayCandidates =
      [ ( scoreValue
        , QI.FindDisplaySpec
            { QI.findDisplayAttribute = identityName
            , QI.findDisplayTargetObject = Just (objectName linkedObject)
            , QI.findDisplayLinkRole = Just (lastLinkName pathValue)
            , QI.findDisplayLabel = Just (roleDisplayLabel rawField pathValue linkedObject identityName)
            }
        )
      | pathValue <- findAllPathsFrom ontology 2 (objectName factObjectValue)
      , Just linkedObject <- [findObject ontology (OG.targetObjectName pathValue)]
      , Just identityName <- [roleIdentityDimension linkedObject]
      , Just identityAttribute <- [findAttribute linkedObject identityName]
      , isPublicFindDisplayAttribute identityAttribute
      , let scoreValue = roleDisplayScore rawField pathValue linkedObject identityName
      , scoreValue > 0
      ]
    roleDisplayRank (scoreValue, displaySpec) =
      (Down scoreValue, QI.findDisplayAttribute displaySpec)

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

roleDisplayScore :: Text -> DiscoveredPath -> Object -> Text -> Int
roleDisplayScore rawField pathValue linkedObject identityName =
  maximum (0 : [score | (aliasValue, score) <- roleDisplayAliases pathValue linkedObject identityName, aliasValue == rawKey])
  where
    rawKey = normalizedMeasureKey rawField

roleDisplayAliases :: DiscoveredPath -> Object -> Text -> [(Text, Int)]
roleDisplayAliases pathValue linkedObject identityName =
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
          fromLink = T.replace sourceObjectKey "" (T.replace targetKey "" linkKey)
          fromSourceKey = T.replace "id" "" (T.replace targetKey "" sourceKeyValue)
       in if fromLink /= "" then fromLink else fromSourceKey
    [] -> ""

maybeLastStep :: DiscoveredPath -> [OG.PathStep]
maybeLastStep pathValue =
  case reverse (steps pathValue) of
    stepValue : _ -> [stepValue]
    [] -> []

roleDisplayLabel :: Text -> DiscoveredPath -> Object -> Text -> Text
roleDisplayLabel rawField pathValue linkedObject identityName =
  case roleDisplayScore rawField pathValue linkedObject identityName of
    scoreValue | scoreValue >= 110 -> normalizedRoleKey pathValue linkedObject
    _ -> normalizedSqlLabel rawField

normalizedSqlLabel :: Text -> Text
normalizedSqlLabel rawField =
  case normalizedMeasureKey rawField of
    "" -> "display_value"
    labelValue -> labelValue

isPublicFindDisplayAttribute :: OT.Attribute -> Bool
isPublicFindDisplayAttribute attributeValue =
  attributeVisibility attributeValue == Public
    && attributeKind attributeValue `elem` [Dimension, Measure]

resolveFindOrders :: Ontology -> Object -> [Object] -> Object -> [DraftOrder] -> Maybe Text -> [QI.FindDisplaySpec] -> Maybe [QI.FindOrderSpec]
resolveFindOrders ontology targetObject actorObjects factObjectValue draftOrders maybeSort displaySpecs =
  case draftOrders of
    [] ->
      case maybeSort of
        Nothing -> Just []
        Just sortValue -> do
          displaySpec <- firstDisplaySpec displaySpecs
          directionValue <- normalizeFindOrderDirection (Just sortValue)
          Just [QI.FindOrderSpec {QI.findOrderField = displaySpec, QI.findOrderDirection = directionValue}]
    _ -> mapM resolveFindOrder draftOrders
  where
    resolveFindOrder orderValue = do
      fieldSpec <-
        case orderBy orderValue of
          Just fieldValue -> resolveFindDisplaySpec ontology targetObject actorObjects factObjectValue fieldValue
          Nothing -> firstDisplaySpec displaySpecs
      directionValue <- normalizeFindOrderDirection (orderDirection orderValue <|> maybeSort)
      Just
        QI.FindOrderSpec
          { QI.findOrderField = fieldSpec
          , QI.findOrderDirection = directionValue
          }

firstDisplaySpec :: [QI.FindDisplaySpec] -> Maybe QI.FindDisplaySpec
firstDisplaySpec displaySpecs =
  case displaySpecs of
    displaySpec : _ -> Just displaySpec
    [] -> Nothing

normalizeFindOrderDirection :: Maybe Text -> Maybe QI.FindOrderDirection
normalizeFindOrderDirection maybeDirection =
  case normalizedKey <$> maybeDirection of
    Nothing -> Just QI.FindOrderDesc
    Just "" -> Just QI.FindOrderDesc
    Just "desc" -> Just QI.FindOrderDesc
    Just "descending" -> Just QI.FindOrderDesc
    Just "newest" -> Just QI.FindOrderDesc
    Just "newestfirst" -> Just QI.FindOrderDesc
    Just "latest" -> Just QI.FindOrderDesc
    Just "latestfirst" -> Just QI.FindOrderDesc
    Just "highest" -> Just QI.FindOrderDesc
    Just "most" -> Just QI.FindOrderDesc
    Just "asc" -> Just QI.FindOrderAsc
    Just "ascending" -> Just QI.FindOrderAsc
    Just "oldest" -> Just QI.FindOrderAsc
    Just "oldestfirst" -> Just QI.FindOrderAsc
    Just "earliest" -> Just QI.FindOrderAsc
    Just "earliestfirst" -> Just QI.FindOrderAsc
    Just "lowest" -> Just QI.FindOrderAsc
    Just "least" -> Just QI.FindOrderAsc
    _ -> Nothing
