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
import QueryModel.SemanticDraft.MeasureMatch (bestPublicMeasureAttributeMatch, measureAttributeScore)
import QueryModel.SemanticDraft.Normalize
import QueryModel.SemanticDraft.Types

semanticFindDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticFindDraftToQuery ontology draft = do
  -- Turn a find draft into typed Query IR for row retrieval.
  -- The fact object is selected by ontology paths and filter support.
  targetObject <- resolveSubjectObject ontology (subject draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  findTimeScopeValue <- findTimeScope (timeWindow draft) (filters draft)
  let predicateDraftFilters = findPredicateDraftFilters (filters draft)
      maybeDraftPredicateTree = predicate draft
  requireFindRequest predicateDraftFilters maybeDraftPredicateTree findTimeScopeValue
  grounded <- resolveFindGrounding ontology draft targetObject predicateDraftFilters maybeDraftPredicateTree findTimeScopeValue limitValue
  pure (findQuery grounded)

resolveFindGrounding :: Ontology -> SemanticDraft -> Object -> [DraftFilter] -> Maybe DraftPredicate -> TimeScope -> Maybe Int -> Either Text GroundedFind
resolveFindGrounding ontology draft targetObject predicateDraftFilters maybeDraftPredicateTree findTimeScopeValue limitValue =
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
          (groundFindFactCandidate ontology draft targetObject actorObjects predicateDraftFilters maybeDraftPredicateTree findTimeScopeValue limitValue)
          (objects ontology)
    actorObjects = findActorObjects ontology targetObject (predicateDraftFilters <> draftPredicateIdentityFilters maybeDraftPredicateTree)

findCandidateRank :: GroundedFind -> (Down Int, Text)
findCandidateRank candidate =
  (Down (findMatchScore candidate), objectName (findFactObject candidate))

groundFindFactCandidate :: Ontology -> SemanticDraft -> Object -> [Object] -> [DraftFilter] -> Maybe DraftPredicate -> TimeScope -> Maybe Int -> Object -> Maybe GroundedFind
groundFindFactCandidate ontology draft targetObject actorObjects predicateDraftFilters maybeDraftPredicateTree findTimeScopeValue limitValue factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName targetObject)
  _ <- requireFindTimeScopeFactSurface findTimeScopeValue factObjectValue
  filterPredicateTree <- groundDraftFindFiltersPredicateTree ontology targetObject actorObjects factObjectValue predicateDraftFilters
  directPredicateTree <- mapM (groundDraftFindPredicateTree ontology targetObject actorObjects factObjectValue) maybeDraftPredicateTree
  displayDimensionValue <- identityDimension targetObject
  let predicateTree = combinePredicates (maybe [] pure filterPredicateTree <> maybe [] pure directPredicateTree)
  pure
    GroundedFind
      { findFactObject = factObjectValue
      , findTargetObject = targetObject
      , findDisplayDimensions = findDisplayDimensionsFor targetObject displayDimensionValue
      , findPredicateTreeValue = predicateTree
      , findFilterValues = timeScopeFilters findTimeScopeValue
      , findLimitValue = limitValue
      , findAssumptions = assumptions draft
      , findMatchScore = findFactCandidateScore factObjectValue targetObject actorObjects predicateTree
      }

findPredicateDraftFilters :: [DraftFilter] -> [DraftFilter]
findPredicateDraftFilters =
  filter (not . draftFilterIsTimeScopeFilter)

requireFindRequest :: [DraftFilter] -> Maybe DraftPredicate -> TimeScope -> Either Text ()
requireFindRequest predicateDraftFilters maybeDraftPredicateTree findTimeScopeValue =
  case (predicateDraftFilters, maybeDraftPredicateTree, findTimeScopeValue) of
    ([], Nothing, AllAvailable) -> Left "Find drafts require at least one user-facing filter or a bounded time scope."
    _ -> pure ()

requireFindTimeScopeFactSurface :: TimeScope -> Object -> Maybe ()
requireFindTimeScopeFactSurface findTimeScopeValue factObjectValue =
  case findTimeScopeValue of
    AllAvailable -> Just ()
    PastYear -> do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    LastNDays _ -> do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    DateRange _ _ -> do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    RecentGames _ seasonFilters -> do
      _ <- findAttribute factObjectValue "game_date"
      case seasonFilters of
        [] -> Just ()
        _ -> do
          _ <- findAttribute factObjectValue "season_year"
          _ <- findAttribute factObjectValue "season_type"
          Just ()
    ExactSeason _ _ -> do
      _ <- findAttribute factObjectValue "season_year"
      _ <- findAttribute factObjectValue "season_type"
      Just ()
    SeasonTypeOnly _ -> do
      _ <- findAttribute factObjectValue "season_type"
      Just ()

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

combinePredicates :: [QI.Predicate] -> Maybe QI.Predicate
combinePredicates predicateValues =
  case predicateValues of
    [] -> Nothing
    [predicateValue] -> Just predicateValue
    _ -> Just (QI.PredicateAnd predicateValues)

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

normalizePredicateOperator :: Maybe Text -> Maybe QI.PredicateOperator
normalizePredicateOperator maybeRawOp =
  case T.strip <$> maybeRawOp of
    Just "=" -> Just QI.PredicateEquals
    Just "!=" -> Just QI.PredicateNotEquals
    Just "<>" -> Just QI.PredicateNotEquals
    Just ">" -> Just QI.PredicateGreaterThan
    Just ">=" -> Just QI.PredicateGreaterThanOrEqual
    Just "<" -> Just QI.PredicateLessThan
    Just "<=" -> Just QI.PredicateLessThanOrEqual
    _ ->
      case normalizedKey <$> maybeRawOp of
        Nothing -> Just QI.PredicateEquals
        Just "" -> Just QI.PredicateEquals
        Just "eq" -> Just QI.PredicateEquals
        Just "equals" -> Just QI.PredicateEquals
        Just "is" -> Just QI.PredicateEquals
        Just "notequals" -> Just QI.PredicateNotEquals
        Just "not" -> Just QI.PredicateNotEquals
        Just "neq" -> Just QI.PredicateNotEquals
        Just "over" -> Just QI.PredicateGreaterThan
        Just "above" -> Just QI.PredicateGreaterThan
        Just "greaterthan" -> Just QI.PredicateGreaterThan
        Just "gt" -> Just QI.PredicateGreaterThan
        Just "morethan" -> Just QI.PredicateGreaterThan
        Just "atleast" -> Just QI.PredicateGreaterThanOrEqual
        Just "gte" -> Just QI.PredicateGreaterThanOrEqual
        Just "under" -> Just QI.PredicateLessThan
        Just "below" -> Just QI.PredicateLessThan
        Just "lessthan" -> Just QI.PredicateLessThan
        Just "lt" -> Just QI.PredicateLessThan
        Just "atmost" -> Just QI.PredicateLessThanOrEqual
        Just "lte" -> Just QI.PredicateLessThanOrEqual
        Just "in" -> Just QI.PredicateIn
        Just "notin" -> Just QI.PredicateNotIn
        Just "between" -> Just QI.PredicateBetween
        Just "contains" -> Just QI.PredicateContains
        _ -> Nothing

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
      , QI.findPredicateTree = findPredicateTreeValue grounded
      , QI.findFilters = findFilterValues grounded
      , QI.findLimit = findLimitValue grounded
      , QI.findAssumptions = findAssumptions grounded
      }
