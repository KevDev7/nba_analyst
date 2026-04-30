{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}
{-# LANGUAGE TupleSections #-}

module QueryModel.SemanticDraft.Find.Predicate
  ( draftPredicateIdentityFilters
  , findActorObjects
  , findFactCandidateScore
  , groundDraftFindFiltersPredicateTree
  , groundDraftFindPredicateTree
  , resolveFindPredicateAttribute
  ) where

import Data.List (nub, sortOn)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (AttributeVisibility (Public), Object, Ontology (objects))
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.MeasureMatch (bestPublicMeasureAttributeMatch, measureAttributeScore)
import QueryModel.SemanticDraft.Normalize
import QueryModel.SemanticDraft.PredicateGrounding (combinePredicates, normalizePredicateOperator)
import QueryModel.SemanticDraft.Types

groundDraftFindFiltersPredicateTree :: Ontology -> Object -> [Object] -> Object -> [DraftFilter] -> Maybe (Maybe QI.Predicate)
groundDraftFindFiltersPredicateTree ontology targetObject actorObjects factObjectValue draftFilters = do
  predicateValues <- mapM (groundDraftFindFilterPredicate ontology targetObject actorObjects factObjectValue) draftFilters
  Just (combinePredicates predicateValues)

groundDraftFindFilterPredicate :: Ontology -> Object -> [Object] -> Object -> DraftFilter -> Maybe QI.Predicate
groundDraftFindFilterPredicate ontology targetObject actorObjects factObjectValue draftFilter = do
  rawField <- filterField draftFilter
  rawValue <- filterValue draftFilter
  opValue <- normalizePredicateOperator (filterOp draftFilter)
  (predicateObject, predicateAttribute) <- resolveFindPredicateAttribute ontology targetObject actorObjects factObjectValue rawField
  pure
    ( QI.PredicateLeaf
        QI.PredicateField
          { QI.predicateFieldTargetObject = objectName predicateObject
          , QI.predicateFieldAttribute = attributeName predicateAttribute
          , QI.predicateLocation = QI.PredicateRowField
          }
        opValue
        (QI.PredicateScalar rawValue)
    )

groundDraftFindPredicateTree :: Ontology -> Object -> [Object] -> Object -> DraftPredicate -> Maybe QI.Predicate
groundDraftFindPredicateTree ontology targetObject actorObjects factObjectValue draftPredicate =
  case draftPredicate of
    DraftPredicateLeaf {draftPredicateField = rawField, draftPredicateOp = maybeRawOp, draftPredicateValue = rawValue} -> do
      opValue <- normalizePredicateOperator maybeRawOp
      (predicateObject, predicateAttribute) <- resolveFindPredicateAttribute ontology targetObject actorObjects factObjectValue rawField
      pure
        ( QI.PredicateLeaf
            QI.PredicateField
              { QI.predicateFieldTargetObject = objectName predicateObject
              , QI.predicateFieldAttribute = attributeName predicateAttribute
              , QI.predicateLocation = QI.PredicateRowField
              }
            opValue
            rawValue
        )
    DraftPredicateAnd predicatesValue ->
      QI.PredicateAnd <$> mapM (groundDraftFindPredicateTree ontology targetObject actorObjects factObjectValue) predicatesValue
    DraftPredicateOr predicatesValue ->
      QI.PredicateOr <$> mapM (groundDraftFindPredicateTree ontology targetObject actorObjects factObjectValue) predicatesValue
    DraftPredicateNot predicateValue ->
      QI.PredicateNot <$> groundDraftFindPredicateTree ontology targetObject actorObjects factObjectValue predicateValue

resolveFindPredicateAttribute :: Ontology -> Object -> [Object] -> Object -> Text -> Maybe (Object, OT.Attribute)
resolveFindPredicateAttribute ontology targetObject actorObjects factObjectValue rawField =
  case objectIdentityAttributeMatch ontology factObjectValue rawField of
    Just matchValue -> Just matchValue
    Nothing ->
      case bestReachableAttributeMatch ontology targetObject actorObjects factObjectValue rawField of
        Just matchValue -> Just matchValue
        Nothing -> factMeasureAttributeMatch factObjectValue rawField

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

factMeasureAttributeMatch :: Object -> Text -> Maybe (Object, OT.Attribute)
factMeasureAttributeMatch factObjectValue rawField =
  (factObjectValue,) <$> bestPublicMeasureAttributeMatch rawField factObjectValue

findAttributeScore :: Object -> [Object] -> Object -> Text -> OT.Attribute -> Int
findAttributeScore targetObject actorObjects factObjectValue rawField attributeValue
  | attributeKey `elem` rawKeys = 100
  | T.replace "total" "" attributeKey `elem` rawKeys = 90
  | T.replace "team" "" attributeKey `elem` rawKeys = 85
  | any (`T.isSuffixOf` attributeKey) rawKeys = 80
  | measureAttributeScore rawField factObjectValue attributeValue > 0 = measureAttributeScore rawField factObjectValue attributeValue
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
  case (normalizePredicateOperator (filterOp draftFilter), filterValue draftFilter) of
    (Just QI.PredicateEquals, Just (QI.FilterText textValue)) -> T.strip textValue /= ""
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

draftPredicateIdentityFilters :: Maybe DraftPredicate -> [DraftFilter]
draftPredicateIdentityFilters maybeDraftPredicate =
  case maybeDraftPredicate of
    Nothing -> []
    Just draftPredicate -> draftPredicateIdentityFiltersFromTree draftPredicate

draftPredicateIdentityFiltersFromTree :: DraftPredicate -> [DraftFilter]
draftPredicateIdentityFiltersFromTree draftPredicate =
  case draftPredicate of
    DraftPredicateLeaf {draftPredicateField = rawField, draftPredicateOp = maybeRawOp, draftPredicateValue = rawValue} ->
      case normalizePredicateOperator maybeRawOp of
        Just QI.PredicateEquals ->
          [ DraftFilter
              { filterField = Just rawField
              , filterOp = Just "="
              , filterValue = Just (QI.FilterText textValue)
              }
          | textValue <- predicateTextValues rawValue
          ]
        Just QI.PredicateIn ->
          [ DraftFilter
              { filterField = Just rawField
              , filterOp = Just "="
              , filterValue = Just (QI.FilterText textValue)
              }
          | textValue <- predicateTextValues rawValue
          ]
        _ -> []
    DraftPredicateAnd predicateValues -> concatMap draftPredicateIdentityFiltersFromTree predicateValues
    DraftPredicateOr predicateValues -> concatMap draftPredicateIdentityFiltersFromTree predicateValues
    DraftPredicateNot _ -> []

predicateTextValues :: QI.PredicateValue -> [Text]
predicateTextValues predicateValue =
  case predicateValue of
    QI.PredicateScalar (QI.FilterText textValue) -> [textValue]
    QI.PredicateScalar _ -> []
    QI.PredicateList values ->
      [ textValue
      | QI.FilterText textValue <- values
      ]
    QI.PredicateRange _ _ -> []

findFactCandidateScore :: Object -> Object -> [Object] -> Maybe QI.Predicate -> Int
findFactCandidateScore factObjectValue targetObject actorObjects maybePredicateTree =
  subjectFactAffinity targetObject factObjectValue
    + actorFactAffinity actorObjects factObjectValue
    + (10 * countFactObjectPredicateLeaves factObjectValue maybePredicateTree)

countFactObjectPredicateLeaves :: Object -> Maybe QI.Predicate -> Int
countFactObjectPredicateLeaves factObjectValue maybePredicateTree =
  case maybePredicateTree of
    Nothing -> 0
    Just predicateTree -> countFactObjectPredicateLeavesFromTree predicateTree
  where
    countFactObjectPredicateLeavesFromTree predicateTree =
      case predicateTree of
        QI.PredicateLeaf fieldValue _ _ ->
          if QI.predicateFieldTargetObject fieldValue == objectName factObjectValue
            then 1
            else 0
        QI.PredicateAnd predicateValues -> sum (map countFactObjectPredicateLeavesFromTree predicateValues)
        QI.PredicateOr predicateValues -> sum (map countFactObjectPredicateLeavesFromTree predicateValues)
        QI.PredicateNot predicateValue -> countFactObjectPredicateLeavesFromTree predicateValue

actorFactAffinity :: [Object] -> Object -> Int
actorFactAffinity actorObjects factObjectValue =
  maximum
    ( 0
        : [ 75
          | actorObject <- actorObjects
          , normalizedKey (objectName actorObject) `T.isInfixOf` normalizedKey (objectName factObjectValue)
          ]
    )

reachableObjects :: Ontology -> Object -> [Object]
reachableObjects ontology objectValue =
  [ candidateObject
  | candidateObject <- objects ontology
  , objectName candidateObject /= objectName objectValue
  , findPath ontology 2 (objectName objectValue) (objectName candidateObject) /= Nothing
  ]
