{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Rank (semanticRankDraftToQuery) where

import Data.Text (Text)
import OntologyLayer.Graph (findPath)
import OntologyLayer.Types (Ontology, Object)
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.CandidateSelection
import QueryModel.SemanticDraft.FilterGrounding (groundDraftRowPredicate)
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Grouping (groupingIdentityDimension, requireGroupingDimensionReachable, resolveGroupingDimensionValue)
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.ResultFilterGrounding (groundDraftResultPredicate)
import QueryModel.SemanticDraft.Types

semanticRankDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticRankDraftToQuery ontology draft = do
  -- Turn a ranking draft into typed Query IR.
  -- This function checks the rank-specific pieces, grounds them, then builds IR.
  rawMeasure <- requireDraftMeasure draft
  rankingTimeScopeValue <- rankingTimeScope (timeWindow draft) (filters draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  orderBuilder <- requireRankingSort (sort draft)
  subjectObject <- resolveSubjectObject ontology (subject draft)
  rankingDimensions <- resolveRankingDimensions ontology subjectObject (dimensions draft)
  grounded <- resolveRankingGrounding ontology draft rawMeasure subjectObject rankingDimensions rankingTimeScopeValue limitValue
  pure (rankingQuery orderBuilder grounded)

resolveRankingDimensions :: Ontology -> Object -> [Text] -> Either Text [SemanticGroupingDimension]
resolveRankingDimensions ontology subjectObject rawDimensions = do
  -- Ranking rows start from the subject identity. Extra dimensions refine the
  -- rank grain, e.g. Team + Season Type, without losing the ranked subject.
  identityValue <- groupingIdentityDimension subjectObject
  resolvedDimensions <- mapM (resolveGroupingDimensionValue ontology subjectObject) rawDimensions
  let identityName = groupingDimensionName identityValue
      alreadyIncludesIdentity =
        any ((== identityName) . groupingDimensionName) resolvedDimensions
  pure $
    case resolvedDimensions of
      [] -> [identityValue]
      _ ->
        if alreadyIncludesIdentity
          then resolvedDimensions
          else identityValue : resolvedDimensions

resolveRankingGrounding :: Ontology -> SemanticDraft -> Text -> Object -> [SemanticGroupingDimension] -> TimeScope -> Maybe Int -> Either Text GroundedRanking
resolveRankingGrounding ontology draft rawMeasure subjectObject rankingDimensions rankingTimeScopeValue maybeLimit =
  -- Search the ontology for the best fact object + metric + display dimension
  -- that can answer this ranking.
  selectMetricFactGrounding
    failureMessage
    ontology
    rawMeasure
    (draftMeasurePhrases draft)
    rankingCandidateEligibility
    groundRankedCandidate
  where
    failureMessage =
      "Could not ground ranking draft with subject '"
        <> subject draft
        <> "', measure '"
        <> rawMeasure
        <> "', and the requested rank filters against executable ontology metrics."
    rankingCandidateEligibility factObjectValue = do
      _ <- findPath ontology 2 (objectName factObjectValue) (objectName subjectObject)
      mapM_ (requireGroupingDimensionReachable ontology factObjectValue . groupingDimensionName) rankingDimensions
      _ <- requireTimeScopeFactSurface rankingTimeScopeValue factObjectValue
      let dimensionObjects = map groupingDimensionObject rankingDimensions
      pure
        ( maximum
            (subjectFactAffinity subjectObject factObjectValue : map (`subjectFactAffinity` factObjectValue) dimensionObjects)
        )
    groundRankedCandidate candidate =
      groundFactCandidate ontology draft subjectObject rankingDimensions rankingTimeScopeValue maybeLimit candidate

groundFactCandidate :: Ontology -> SemanticDraft -> Object -> [SemanticGroupingDimension] -> TimeScope -> Maybe Int -> MetricFactCandidate -> Maybe GroundedRanking
groundFactCandidate ontology draft subjectObject rankingDimensions rankingTimeScopeValue maybeLimit candidate = do
  -- A fact candidate must be connected to the subject, expose the requested
  -- time surface, have a matching executable metric, and have a display field.
  dimensionValue <-
    case rankingDimensions of
      rankingDimension : _ -> Just (groupingDimensionName rankingDimension)
      [] -> identityDimension subjectObject
  rowPredicateTree <- groundDraftRowPredicate ontology factObjectValue (filters draft) (predicate draft)
  resultPredicateTree <- groundDraftResultPredicate factObjectValue metricValue (resultFilters draft) (resultPredicate draft)
  pure
    GroundedRanking
      { factObject = factObjectValue
      , subjectObject = subjectObject
      , metricDef = metricValue
      , metricDefs = metricValues
      , displayDimension = dimensionValue
      , displayDimensions = map groupingDimensionName rankingDimensions
      , filterValues = timeScopeFilters rankingTimeScopeValue
      , rowPredicateValue = rowPredicateTree
      , resultPredicateValue = resultPredicateTree
      , limitValue = maybeLimit
      , assumptionValues = assumptions draft
      , matchScore = candidateMatchScore candidate
      , subjectAffinityScore = candidateAffinityScore candidate
      }
  where
    factObjectValue = candidateFactObject candidate
    metricValue = candidateMetricDef candidate
    metricValues = candidateMetricDefs candidate

rankingQuery :: (QI.MetricName -> QI.Order) -> GroundedRanking -> QI.Query
rankingQuery orderBuilder grounded =
  -- Build the typed Query IR consumed by GroundedPlanning.
  -- This is where user-facing draft language becomes ontology-backed structure.
  QI.MetricQuery
    QI.MetricQuerySpec
      { QI.sharedQuery =
          QI.BaseQuery
            { QI.coreFactObject = objectName (factObject grounded)
            , QI.metrics = map metricName (metricDefs grounded)
            , QI.dimensions = displayDimensions grounded
            , QI.timeGrain = Nothing
            , QI.filters = filterValues grounded
            , QI.rowPredicate = rowPredicateValue grounded
            , QI.resultPredicate = resultPredicateValue grounded
            , QI.orders = [orderBuilder (metricName (metricDef grounded))]
            , QI.limit = limitValue grounded
            , QI.assumptions = assumptionValues grounded
            }
      , QI.entityFilters = []
      , QI.comparison = Nothing
      }
