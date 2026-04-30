{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.Build.Object (semanticObjectDraftToQuery) where

import Data.Text (Text)
import OntologyLayer.Graph (findPath)
import OntologyLayer.Types (Object, Ontology)
import qualified QueryModel.IR as QI
import QueryModel.SemanticConstruction.CandidateSelection
import QueryModel.SemanticConstruction.Match
import QueryModel.SemanticConstruction.Types
import QueryModel.SemanticConstruction.FilterGrounding (groundDraftRowPredicate)
import QueryModel.SemanticConstruction.TimeScope (objectTimeScope, timeScopeFilters)
import QueryModel.SemanticDraft.Filters (draftMeasurePhrases, requireDraftMeasureForFamily, requireOptionalPositiveLimit, requireRankingSort)
import QueryModel.SemanticConstruction.ResultFilterGrounding (groundDraftResultPredicate)
import QueryModel.SemanticDraft.Types

semanticObjectDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticObjectDraftToQuery ontology draft = do
  -- Turn an object draft into typed ObjectQuery IR.
  -- Object questions are entity-row questions: one row per Player/Team/etc.,
  -- with requested metrics attached from the best ontology fact surface.
  rawMeasure <- requireDraftMeasureForFamily "Object" draft
  objectTimeScopeValue <- objectTimeScope (timeWindow draft) (filters draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  orderBuilder <- requireRankingSort (sort draft)
  rowObject <- resolveSubjectObject ontology (subject draft)
  grounded <- resolveObjectGrounding ontology draft rawMeasure rowObject objectTimeScopeValue limitValue
  pure (objectQuery orderBuilder grounded)

resolveObjectGrounding :: Ontology -> SemanticDraft -> Text -> Object -> TimeScope -> Maybe Int -> Either Text GroundedRanking
resolveObjectGrounding ontology draft rawMeasure rowObject objectTimeScopeValue maybeLimit =
  -- Search ontology fact objects for one that can attach the requested metric
  -- to the requested row object.
  selectMetricFactGrounding
    failureMessage
    ontology
    rawMeasure
    (draftMeasurePhrases draft)
    objectCandidateEligibility
    (groundObjectFactCandidate ontology draft rowObject objectTimeScopeValue maybeLimit)
  where
    failureMessage =
      "Could not ground object draft with subject '"
        <> subject draft
        <> "', measure '"
        <> rawMeasure
        <> "', and the requested object-row filters against executable ontology metrics."
    objectCandidateEligibility factObjectValue = do
      _ <- findPath ontology 2 (objectName factObjectValue) (objectName rowObject)
      _ <- requireTimeScopeFactSurface objectTimeScopeValue factObjectValue
      let affinity = subjectFactAffinity rowObject factObjectValue
      if affinity >= 120
        then Just affinity
        else Nothing

groundObjectFactCandidate :: Ontology -> SemanticDraft -> Object -> TimeScope -> Maybe Int -> MetricFactCandidate -> Maybe GroundedRanking
groundObjectFactCandidate ontology draft rowObject objectTimeScopeValue maybeLimit candidate = do
  dimensionValue <- identityDimension rowObject
  rowPredicateTree <- groundDraftRowPredicate ontology factObjectValue (filters draft) (predicate draft)
  resultPredicateTree <- groundDraftResultPredicate factObjectValue metricValue (resultFilters draft) (resultPredicate draft)
  pure
    GroundedRanking
      { factObject = factObjectValue
      , subjectObject = rowObject
      , metricDef = metricValue
      , metricDefs = metricValues
      , displayDimension = dimensionValue
      , displayDimensions = [dimensionValue]
      , filterValues = timeScopeFilters objectTimeScopeValue
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

objectQuery :: (QI.MetricName -> QI.Order) -> GroundedRanking -> QI.Query
objectQuery orderBuilder grounded =
  QI.ObjectQuery
    QI.ObjectQuerySpec
      { QI.rowObject = objectName (subjectObject grounded)
      , QI.sharedQuery =
          QI.BaseQuery
            { QI.coreFactObject = objectName (factObject grounded)
            , QI.metrics = map metricName (metricDefs grounded)
            , QI.dimensions = [displayDimension grounded]
            , QI.timeGrain = Nothing
            , QI.filters = filterValues grounded
            , QI.rowPredicate = rowPredicateValue grounded
            , QI.resultPredicate = resultPredicateValue grounded
            , QI.orders = [orderBuilder (metricName (metricDef grounded))]
            , QI.limit = limitValue grounded
            , QI.assumptions = assumptionValues grounded
            }
      }
