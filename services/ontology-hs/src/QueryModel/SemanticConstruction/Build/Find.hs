{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.Build.Find (semanticFindDraftToQuery) where

import Data.List (sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (Object, Ontology (objects))
import qualified QueryModel.IR as QI
import QueryModel.SemanticConstruction.Find.Display (resolveFindDisplayDimensions, resolveFindOrders)
import QueryModel.SemanticConstruction.Find.Predicate
import QueryModel.SemanticConstruction.Match
import QueryModel.SemanticConstruction.Types
import QueryModel.SemanticConstruction.PredicateGrounding (combinePredicates)
import QueryModel.SemanticConstruction.TimeScope (draftFilterIsTimeScopeFilter, findTimeScope, timeScopeFilters)
import QueryModel.SemanticDraft.Filters (requireOptionalPositiveLimit)
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
  displayDimensionValues <- resolveFindDisplayDimensions ontology targetObject actorObjects factObjectValue (dimensions draft) displayDimensionValue
  findOrderValues <- resolveFindOrders ontology targetObject actorObjects factObjectValue (order draft) (sort draft) displayDimensionValues
  let predicateTree = combinePredicates (maybe [] pure filterPredicateTree <> maybe [] pure directPredicateTree)
  pure
    GroundedFind
      { findFactObject = factObjectValue
      , findTargetObject = targetObject
      , findDisplayDimensions = displayDimensionValues
      , findOrderValues = findOrderValues
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

findQuery :: GroundedFind -> QI.Query
findQuery grounded =
    QI.FindQuery
    QI.FindQuerySpec
      { QI.findCoreFactObject = objectName (findFactObject grounded)
      , QI.findTargetObject = objectName (findTargetObject grounded)
      , QI.findDisplayDimensions = findDisplayDimensions grounded
      , QI.findOrders = findOrderValues grounded
      , QI.findPredicateTree = findPredicateTreeValue grounded
      , QI.findFilters = findFilterValues grounded
      , QI.findLimit = findLimitValue grounded
      , QI.findAssumptions = findAssumptions grounded
      }
