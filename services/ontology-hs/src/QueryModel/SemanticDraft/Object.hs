{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Object (semanticObjectDraftToQuery) where

import Data.List (sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import OntologyLayer.Graph (findPath)
import OntologyLayer.Types (Object, Ontology (objects))
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.FilterGrounding (groundDraftRowPredicate)
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.ResultFilterGrounding (groundDraftResultPredicate)
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
  case rankedCandidates of
    candidate : _ -> Right candidate
    [] ->
      Left
        ( "Could not ground object draft with subject '"
            <> subject draft
            <> "', measure '"
            <> rawMeasure
            <> "', and the requested object-row filters against executable ontology metrics."
        )
  where
    rankedCandidates =
      sortOn objectCandidateRank $
        mapMaybe
          (groundObjectFactCandidate ontology draft rawMeasure rowObject objectTimeScopeValue maybeLimit)
          (objects ontology)

objectCandidateRank :: GroundedRanking -> (Down Int, Down Int, Text)
objectCandidateRank candidate =
  ( Down (matchScore candidate)
  , Down (subjectAffinityScore candidate)
  , objectName (factObject candidate)
  )

groundObjectFactCandidate :: Ontology -> SemanticDraft -> Text -> Object -> TimeScope -> Maybe Int -> Object -> Maybe GroundedRanking
groundObjectFactCandidate ontology draft rawMeasure rowObject objectTimeScopeValue maybeLimit factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName rowObject)
  _ <- requireTimeScopeFactSurface objectTimeScopeValue factObjectValue
  metricValue <- bestMetricMatch rawMeasure factObjectValue
  metricValues <- mapM (`bestMetricMatch` factObjectValue) (draftMeasurePhrases draft)
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
      , matchScore = metricMatchScore rawMeasure metricValue
      , subjectAffinityScore = subjectFactAffinity rowObject factObjectValue
      }

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
