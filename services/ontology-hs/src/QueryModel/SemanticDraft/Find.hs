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
      -- Pick the fact surface using both ontology reachability and the role
      -- implied by identity filters, like Team in "games where Lakers scored".
      sortOn findCandidateRank $
        mapMaybe
          (groundFindFactCandidate ontology draft targetObject actorObjects findTimeFilters limitValue)
          (objects ontology)
    actorObjects = findActorObjects ontology targetObject (filters draft)

findCandidateRank :: GroundedFind -> (Down Int, Text)
findCandidateRank candidate =
  (Down (findMatchScore candidate), objectName (findFactObject candidate))

groundFindFactCandidate :: Ontology -> SemanticDraft -> Object -> [Object] -> [QI.Filter] -> Maybe Int -> Object -> Maybe GroundedFind
groundFindFactCandidate ontology draft targetObject actorObjects findTimeFilters limitValue factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName targetObject)
  predicateValues <- mapM (resolveFindPredicateForFact ontology targetObject actorObjects factObjectValue) (filters draft)
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
      , findMatchScore = findFactCandidateScore factObjectValue targetObject actorObjects predicateValues
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

findFactCandidateScore :: Object -> Object -> [Object] -> [QI.FindPredicate] -> Int
findFactCandidateScore factObjectValue targetObject actorObjects predicateValues =
  subjectFactAffinity targetObject factObjectValue
    + actorFactAffinity actorObjects factObjectValue
    + (10 * length [predicateValue | predicateValue <- predicateValues, QI.predicateTargetObject predicateValue == objectName factObjectValue])

actorFactAffinity :: [Object] -> Object -> Int
actorFactAffinity actorObjects factObjectValue =
  maximum
    ( 0
        : [ 75
          | actorObject <- actorObjects
          , normalizedKey (objectName actorObject) `T.isInfixOf` normalizedKey (objectName factObjectValue)
          ]
    )

resolveFindPredicateForFact :: Ontology -> Object -> [Object] -> Object -> DraftFilter -> Maybe QI.FindPredicate
resolveFindPredicateForFact ontology targetObject actorObjects factObjectValue draftFilter = do
  rawField <- filterField draftFilter
  rawValue <- filterValue draftFilter
  opValue <- normalizeFindOp (filterOp draftFilter)
  (predicateObject, predicateAttribute) <- resolveFindPredicateAttribute ontology targetObject actorObjects factObjectValue rawField
  pure
    QI.FindPredicate
      { QI.predicateTargetObject = objectName predicateObject
      , QI.predicateAttribute = attributeName predicateAttribute
      , QI.predicateOperator = opValue
      , QI.predicateFilterValue = rawValue
      }

resolveFindPredicateAttribute :: Ontology -> Object -> [Object] -> Object -> Text -> Maybe (Object, OT.Attribute)
resolveFindPredicateAttribute ontology targetObject actorObjects factObjectValue rawField =
  case objectIdentityAttributeMatch ontology factObjectValue rawField of
    Just matchValue -> Just matchValue
    Nothing -> bestReachableAttributeMatch ontology targetObject actorObjects factObjectValue rawField

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

bestReachableAttributeMatch :: Ontology -> Object -> [Object] -> Object -> Text -> Maybe (Object, OT.Attribute)
bestReachableAttributeMatch ontology targetObject actorObjects factObjectValue rawField =
  case sortOn findAttributeRank matches of
    matchValue : _ -> Just matchValue
    [] -> Nothing
  where
    matches =
      [ (objectValue, attributeValue)
      | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
      , attributeValue <- objectAttributes objectValue
      , attributeVisibility attributeValue == Public
      , findAttributeScore targetObject actorObjects factObjectValue rawField attributeValue > 0
      ]
    findAttributeRank (objectValue, attributeValue) =
      ( Down (findAttributeScore targetObject actorObjects factObjectValue rawField attributeValue)
      , if objectName objectValue == objectName factObjectValue then (0 :: Int) else 1
      , objectName objectValue
      , attributeName attributeValue
      )

findAttributeScore :: Object -> [Object] -> Object -> Text -> OT.Attribute -> Int
findAttributeScore targetObject actorObjects factObjectValue rawField attributeValue
  | attributeKey `elem` rawKeys = 100
  | T.replace "total" "" attributeKey `elem` rawKeys = 90
  | T.replace "team" "" attributeKey `elem` rawKeys = 85
  | any (`T.isSuffixOf` attributeKey) rawKeys = 80
  | otherwise = 0
  where
    rawKeys = findFieldAliasKeys targetObject actorObjects factObjectValue rawField
    attributeKey = normalizedMeasureKey (attributeName attributeValue)

findFieldAliasKeys :: Object -> [Object] -> Object -> Text -> [Text]
findFieldAliasKeys targetObject actorObjects factObjectValue rawField =
  nub $
    [rawKey, T.replace "team" "" rawKey]
      <> scoreAliases
      <> teamGamePointsAliases
  where
    rawKey = normalizedMeasureKey rawField
    scoreAliases =
      if rawKey `elem` ["teamscore", "pointsscored", "scoredpoints"]
        then ["score"]
        else []
    teamGamePointsAliases =
      if isTeamGameScoringContext targetObject actorObjects factObjectValue
          && rawKey `elem` ["points", "scored"]
        then ["score"]
        else []

isTeamGameScoringContext :: Object -> [Object] -> Object -> Bool
isTeamGameScoringContext targetObject actorObjects factObjectValue =
  objectName targetObject == "Game"
    && any ((== "Team") . objectName) actorObjects
    && normalizedKey "Team" `T.isInfixOf` normalizedKey (objectName factObjectValue)

findActorObjects :: Ontology -> Object -> [DraftFilter] -> [Object]
findActorObjects ontology targetObject draftFilters =
  nub
    [ objectValue
    | draftFilter <- draftFilters
    , Just rawField <- [filterField draftFilter]
    , isIdentityFilter draftFilter
    , objectValue <- objects ontology
    , objectName objectValue /= objectName targetObject
    , filterNamesObject rawField objectValue
    ]

isIdentityFilter :: DraftFilter -> Bool
isIdentityFilter draftFilter =
  case (normalizeFindOp (filterOp draftFilter), filterValue draftFilter) of
    (Just QI.OpEq, Just (QI.FilterText textValue)) -> T.strip textValue /= ""
    _ -> False

filterNamesObject :: Text -> Object -> Bool
filterNamesObject rawField objectValue =
  case identityDimension objectValue of
    Nothing -> False
    Just identityName ->
      let rawSubjectKey = subjectMatchKey rawField
          rawKey = normalizedKey rawField
          objectKey = normalizedKey (objectName objectValue)
          identityKey = normalizedKey identityName
       in rawSubjectKey == subjectMatchKey (objectName objectValue)
            || rawKey == objectKey
            || rawKey == identityKey
            || rawKey == objectKey <> "name"

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
