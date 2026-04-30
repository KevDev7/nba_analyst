{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.Find.Display
  ( resolveFindDisplayDimensions
  , resolveFindOrders
  ) where

import Control.Applicative ((<|>))
import Data.List (nub)
import Data.Text (Text)
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (AttributeKind (Dimension, Measure), AttributeVisibility (Public), Object, Ontology)
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticConstruction.Find.Predicate (resolveFindPredicateAttribute)
import QueryModel.SemanticConstruction.Find.Role
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
resolveFindRoleDisplaySpec ontology factObjectValue rawField = do
  roleMatch <- resolveRoleIdentityMatch ontology factObjectValue rawField
  Just
    QI.FindDisplaySpec
      { QI.findDisplayAttribute = attributeName (roleIdentityAttribute roleMatch)
      , QI.findDisplayTargetObject = Just (objectName (roleIdentityObject roleMatch))
      , QI.findDisplayLinkRole = Just (roleIdentityLinkRole roleMatch)
      , QI.findDisplayLabel = Just (roleIdentityLabel roleMatch)
      }

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
