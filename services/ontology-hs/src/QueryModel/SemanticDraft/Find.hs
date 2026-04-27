{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Find (semanticFindDraftToQuery) where

import Data.List (nub, sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (AttributeKind (Dimension), AttributeVisibility (Public), Object, Ontology (objects))
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.Normalize
import QueryModel.SemanticDraft.Types

semanticFindDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticFindDraftToQuery ontology draft = do
  -- Turn a find draft into typed Query IR for row retrieval.
  -- The fact object is selected by ontology paths and filter support.
  targetObject <- resolveSubjectObject ontology (subject draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  requireFindFilters (filters draft)
  findTimeFilters <- findWindowFilters (timeWindow draft) (filters draft)
  grounded <- resolveFindGrounding ontology draft targetObject findTimeFilters limitValue
  pure (findQuery grounded)

resolveFindGrounding :: Ontology -> SemanticDraft -> Object -> [QI.Filter] -> Maybe Int -> Either Text GroundedFind
resolveFindGrounding ontology draft targetObject findTimeFilters limitValue =
  case rankedCandidates of
    candidate : _ -> Right candidate
    [] ->
      Left
        ( "Could not ground find draft with subject '"
            <> subject draft
            <> "' and the requested filters against ontology objects, attributes, and links."
        )
  where
    rankedCandidates =
      sortOn findCandidateRank $
        mapMaybe (groundFindFactCandidate ontology draft targetObject findTimeFilters limitValue) (objects ontology)

findCandidateRank :: GroundedFind -> (Down Int, Text)
findCandidateRank candidate =
  (Down (findMatchScore candidate), objectName (findFactObject candidate))

groundFindFactCandidate :: Ontology -> SemanticDraft -> Object -> [QI.Filter] -> Maybe Int -> Object -> Maybe GroundedFind
groundFindFactCandidate ontology draft targetObject findTimeFilters limitValue factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName targetObject)
  predicateValues <- mapM (resolveFindPredicateForFact ontology factObjectValue) (filters draft)
  displayDimensionValue <- identityDimension targetObject
  pure
    GroundedFind
      { findFactObject = factObjectValue
      , findTargetObject = targetObject
      , findDisplayDimensions = findDisplayDimensionsFor targetObject displayDimensionValue
      , findPredicateValues = predicateValues
      , findFilterValues = findTimeFilters
      , findLimitValue = limitValue
      , findAssumptions = assumptions draft
      , findMatchScore = findFactCandidateScore factObjectValue targetObject predicateValues
      }

findDisplayDimensionsFor :: Object -> Text -> [Text]
findDisplayDimensionsFor targetObject identityDimensionValue =
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

findFactCandidateScore :: Object -> Object -> [QI.FindPredicate] -> Int
findFactCandidateScore factObjectValue targetObject predicateValues =
  subjectFactAffinity targetObject factObjectValue
    + (10 * length [predicateValue | predicateValue <- predicateValues, QI.predicateTargetObject predicateValue == objectName factObjectValue])

resolveFindPredicateForFact :: Ontology -> Object -> DraftFilter -> Maybe QI.FindPredicate
resolveFindPredicateForFact ontology factObjectValue draftFilter = do
  rawField <- filterField draftFilter
  rawValue <- filterValue draftFilter
  opValue <- normalizeFindOp (filterOp draftFilter)
  (predicateObject, predicateAttribute) <- resolveFindPredicateAttribute ontology factObjectValue rawField
  pure
    QI.FindPredicate
      { QI.predicateTargetObject = objectName predicateObject
      , QI.predicateAttribute = attributeName predicateAttribute
      , QI.predicateOperator = opValue
      , QI.predicateFilterValue = rawValue
      }

resolveFindPredicateAttribute :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
resolveFindPredicateAttribute ontology factObjectValue rawField =
  case objectIdentityAttributeMatch ontology factObjectValue rawField of
    Just matchValue -> Just matchValue
    Nothing -> bestReachableAttributeMatch ontology factObjectValue rawField

objectIdentityAttributeMatch :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
objectIdentityAttributeMatch ontology factObjectValue rawField =
  case
    [ (objectValue, attributeValue)
    | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
    , subjectMatchKey rawField == subjectMatchKey (objectName objectValue)
    , Just identityName <- [identityDimension objectValue]
    , Just attributeValue <- [findAttribute objectValue identityName]
    ]
    of
    matchValue : _ -> Just matchValue
    [] -> Nothing

bestReachableAttributeMatch :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
bestReachableAttributeMatch ontology factObjectValue rawField =
  case sortOn findAttributeRank matches of
    matchValue : _ -> Just matchValue
    [] -> Nothing
  where
    matches =
      [ (objectValue, attributeValue)
      | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
      , attributeValue <- objectAttributes objectValue
      , attributeVisibility attributeValue == Public
      , findAttributeScore rawField attributeValue > 0
      ]
    findAttributeRank (objectValue, attributeValue) =
      ( Down (findAttributeScore rawField attributeValue)
      , if objectName objectValue == objectName factObjectValue then (0 :: Int) else 1
      , objectName objectValue
      , attributeName attributeValue
      )

findAttributeScore :: Text -> OT.Attribute -> Int
findAttributeScore rawField attributeValue
  | rawKey == attributeKey = 100
  | rawKey == T.replace "total" "" attributeKey = 90
  | rawKey == T.replace "team" "" attributeKey = 85
  | rawKey `T.isSuffixOf` attributeKey = 80
  | otherwise = 0
  where
    rawKey = normalizedMeasureKey rawField
    attributeKey = normalizedMeasureKey (attributeName attributeValue)

reachableObjects :: Ontology -> Object -> [Object]
reachableObjects ontology objectValue =
  [ candidateObject
  | candidateObject <- objects ontology
  , objectName candidateObject /= objectName objectValue
  , findPath ontology 2 (objectName objectValue) (objectName candidateObject) /= Nothing
  ]

findQuery :: GroundedFind -> QI.Query
findQuery grounded =
    QI.FindQuery
    QI.FindQuerySpec
      { QI.findCoreFactObject = objectName (findFactObject grounded)
      , QI.findTargetObject = objectName (findTargetObject grounded)
      , QI.findDisplayDimensions = findDisplayDimensions grounded
      , QI.findPredicates = findPredicateValues grounded
      , QI.findFilters = findFilterValues grounded
      , QI.findLimit = findLimitValue grounded
      , QI.findAssumptions = findAssumptions grounded
      }
