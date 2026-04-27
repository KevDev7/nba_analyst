{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Rank (semanticRankDraftToQuery) where

import Data.List (sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import OntologyLayer.Graph (findPath)
import OntologyLayer.Types (Ontology (objects), Object)
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.FilterGrounding (groundDraftLinkedFilters)
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.Types

semanticRankDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticRankDraftToQuery ontology draft = do
  -- Turn a ranking draft into typed Query IR.
  -- This function checks the rank-specific pieces, grounds them, then builds IR.
  rawMeasure <- requireDraftMeasure draft
  rankingFilters <- requireRankingFilters (timeWindow draft) (filters draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  orderBuilder <- requireRankingSort (sort draft)
  subjectObject <- resolveSubjectObject ontology (subject draft)
  grounded <- resolveRankingGrounding ontology draft rawMeasure subjectObject rankingFilters limitValue
  pure (rankingQuery orderBuilder grounded)

resolveRankingGrounding :: Ontology -> SemanticDraft -> Text -> Object -> RankingFilterBundle -> Maybe Int -> Either Text GroundedRanking
resolveRankingGrounding ontology draft rawMeasure subjectObject rankingFilters maybeLimit =
  -- Search the ontology for the best fact object + metric + display dimension
  -- that can answer this ranking.
  case rankedCandidates of
    candidate : _ -> Right candidate
    [] ->
      Left
        ( "Could not ground ranking draft with subject '"
            <> subject draft
            <> "', measure '"
            <> rawMeasure
            <> "', and the requested rank filters against executable ontology metrics."
        )
  where
    rankedCandidates =
      sortOn candidateRank $
        mapMaybe
          (groundFactCandidate ontology draft rawMeasure subjectObject rankingFilters maybeLimit)
          (objects ontology)

candidateRank :: GroundedRanking -> (Down Int, Down Int, Text)
candidateRank candidate =
  -- Prefer stronger metric matches, then fact objects that naturally match the subject.
  ( Down (matchScore candidate)
  , Down (subjectAffinityScore candidate)
  , objectName (factObject candidate)
  )

groundFactCandidate :: Ontology -> SemanticDraft -> Text -> Object -> RankingFilterBundle -> Maybe Int -> Object -> Maybe GroundedRanking
groundFactCandidate ontology draft rawMeasure subjectObject rankingFilters maybeLimit factObjectValue = do
  -- A fact candidate must be connected to the subject, expose the requested
  -- time surface, have a matching executable metric, and have a display field.
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName subjectObject)
  _ <- requireRankingFactSurface rankingFilters factObjectValue
  metricValue <- bestMetricMatch rawMeasure factObjectValue
  dimensionValue <- identityDimension subjectObject
  linkedFilterValue <- groundDraftLinkedFilters ontology factObjectValue (filters draft)
  pure
    GroundedRanking
      { factObject = factObjectValue
      , subjectObject = subjectObject
      , metricDef = metricValue
      , displayDimension = dimensionValue
      , filterValues = rankingFilterValues rankingFilters
      , linkedFilterValues = linkedFilterValue
      , limitValue = maybeLimit
      , assumptionValues = assumptions draft
      , matchScore = metricMatchScore rawMeasure metricValue
      , subjectAffinityScore = subjectFactAffinity subjectObject factObjectValue
      }

rankingQuery :: (QI.MetricName -> QI.Order) -> GroundedRanking -> QI.Query
rankingQuery orderBuilder grounded =
  -- Build the typed Query IR consumed by GroundedPlanning.
  -- This is where user-facing draft language becomes ontology-backed structure.
  QI.MetricQuery
    QI.MetricQuerySpec
      { QI.sharedQuery =
          QI.BaseQuery
            { QI.coreFactObject = objectName (factObject grounded)
            , QI.metrics = [metricName (metricDef grounded)]
            , QI.dimensions = [displayDimension grounded]
            , QI.timeGrain = Nothing
            , QI.filters = filterValues grounded
            , QI.linkedFilters = linkedFilterValues grounded
            , QI.orders = [orderBuilder (metricName (metricDef grounded))]
            , QI.limit = limitValue grounded
            , QI.assumptions = assumptionValues grounded
            }
      , QI.entityFilters = []
      , QI.comparison = Nothing
      }
