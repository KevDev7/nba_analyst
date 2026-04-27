{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.FilterGrounding
  ( groundDraftLinkedFilters
  ) where

import Control.Applicative ((<|>))
import Data.List (nub, sortOn)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (AttributeKind (Dimension), AttributeVisibility (Public), Object, Ontology (objects))
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Filters (draftFilterTextValue, seasonTypeFromFilter)
import QueryModel.SemanticDraft.Match (attributeName, identityDimension, objectName)
import QueryModel.SemanticDraft.Normalize (normalizedKey, normalizedMeasureKey, subjectMatchKey)
import QueryModel.SemanticDraft.Types (DraftFilter (filterField, filterOp, filterValue))

groundDraftLinkedFilters :: Ontology -> Object -> [DraftFilter] -> Maybe [QI.LinkedFilter]
groundDraftLinkedFilters ontology factObjectValue draftFilters =
  -- Convert remaining user-facing draft filters into ontology-grounded linked
  -- dimension filters. Time/season filters are already handled as QI.filters.
  mapM (groundDraftLinkedFilter ontology factObjectValue) (linkedFilterCandidates draftFilters)

linkedFilterCandidates :: [DraftFilter] -> [DraftFilter]
linkedFilterCandidates =
  filter (not . isTimeOrSeasonFilter)

isTimeOrSeasonFilter :: DraftFilter -> Bool
isTimeOrSeasonFilter draftFilter =
  seasonTypeFromFilter draftFilter /= Nothing
    || maybe False isTimeOrSeasonField (filterField draftFilter)
    || maybe False isSeasonValue (draftFilterTextValue draftFilter)

isTimeOrSeasonField :: Text -> Bool
isTimeOrSeasonField rawField =
  normalizedKey rawField
    `elem` [ "season"
           , "seasonyear"
           , "seasons"
           , "year"
           , "seasontype"
           , "gametype"
           , "lastngames"
           , "pastyear"
           , "timewindow"
           ]

isSeasonValue :: Text -> Bool
isSeasonValue rawValue =
  "season" `T.isInfixOf` normalizedKey rawValue

groundDraftLinkedFilter :: Ontology -> Object -> DraftFilter -> Maybe QI.LinkedFilter
groundDraftLinkedFilter ontology factObjectValue draftFilter = do
  rawField <- filterField draftFilter
  rawValue <- draftFilterTextValue draftFilter
  _ <- requireEqualityOp (filterOp draftFilter)
  _ <- requireTextFilterValue (filterValue draftFilter)
  (targetObjectValue, attributeValue) <- resolveLinkedFilterAttribute ontology factObjectValue rawField
  pure
    QI.LinkedFilter
      { QI.targetObject = objectName targetObjectValue
      , QI.attribute = attributeName attributeValue
      , QI.value = rawValue
      }

requireEqualityOp :: Maybe Text -> Maybe ()
requireEqualityOp maybeRawOp =
  case fmap T.strip maybeRawOp of
    Nothing -> Just ()
    Just "" -> Just ()
    Just "=" -> Just ()
    Just rawOp
      | normalizedKey rawOp `elem` ["eq", "equals", "is"] -> Just ()
    _ -> Nothing

requireTextFilterValue :: Maybe QI.FilterValue -> Maybe ()
requireTextFilterValue maybeValue =
  case maybeValue of
    Just (QI.FilterText textValue)
      | T.strip textValue /= "" -> Just ()
    _ -> Nothing

resolveLinkedFilterAttribute :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
resolveLinkedFilterAttribute ontology factObjectValue rawField =
  objectIdentityAttributeMatch ontology factObjectValue rawField
    <|> bestReachablePublicDimensionMatch ontology factObjectValue rawField

objectIdentityAttributeMatch :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
objectIdentityAttributeMatch ontology factObjectValue rawField =
  case
    [ (objectValue, attributeValue)
    | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
    , subjectMatchKey rawField == subjectMatchKey (objectName objectValue)
    , Just identityName <- [identityDimension objectValue]
    , Just attributeValue <- [findAttribute objectValue identityName]
    , isPublicDimension attributeValue
    ]
    of
    matchValue : _ -> Just matchValue
    [] -> Nothing

bestReachablePublicDimensionMatch :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
bestReachablePublicDimensionMatch ontology factObjectValue rawField =
  case sortOn linkedFilterAttributeRank matches of
    matchValue : _ -> Just matchValue
    [] -> Nothing
  where
    matches =
      [ (objectValue, attributeValue)
      | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
      , attributeValue <- OT.attributes objectValue
      , isPublicDimension attributeValue
      , linkedFilterAttributeScore rawField objectValue attributeValue > 0
      ]
    linkedFilterAttributeRank (objectValue, attributeValue) =
      ( Down (linkedFilterAttributeScore rawField objectValue attributeValue)
      , if objectName objectValue == objectName factObjectValue then (0 :: Int) else 1
      , objectName objectValue
      , attributeName attributeValue
      )

linkedFilterAttributeScore :: Text -> Object -> OT.Attribute -> Int
linkedFilterAttributeScore rawField objectValue attributeValue
  | rawKey == attributeKey = 100
  | rawKey == T.replace objectKey "" attributeKey = 95
  | rawKey `elem` aliasKeys = 90
  | rawKey `T.isSuffixOf` attributeKey = 80
  | otherwise = 0
  where
    rawKey = normalizedMeasureKey rawField
    objectKey = normalizedKey (objectName objectValue)
    attributeKey = normalizedMeasureKey (attributeName attributeValue)
    aliasKeys =
      nub
        [ T.replace "team" "" attributeKey
        , T.replace "player" "" attributeKey
        , T.replace "opponent" "" attributeKey
        ]

reachableObjects :: Ontology -> Object -> [Object]
reachableObjects ontology factObjectValue =
  [ candidateObject
  | candidateObject <- objects ontology
  , objectName candidateObject /= objectName factObjectValue
  , findPath ontology 2 (objectName factObjectValue) (objectName candidateObject) /= Nothing
  ]

isPublicDimension :: OT.Attribute -> Bool
isPublicDimension attributeValue =
  OT.kind attributeValue == Dimension && OT.visibility attributeValue == Public
