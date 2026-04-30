{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Aggregate (semanticAggregateDraftToQuery) where

import Data.Text (Text)
import OntologyLayer.Types (Ontology, Object)
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.CandidateSelection
import QueryModel.SemanticDraft.FilterGrounding (groundDraftRowPredicate)
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Grouping (requireGroupingDimensionReachable, resolveDefaultGroupingDimensions)
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.ResultFilterGrounding (groundDraftResultPredicate)
import QueryModel.SemanticDraft.Types

semanticAggregateDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticAggregateDraftToQuery ontology draft = do
  -- Turn an aggregate draft into typed Query IR.
  -- Aggregates are grouped summaries, not disguised Top-N rankings.
  rawMeasure <- requireDraftMeasureForFamily "Aggregate" draft
  aggregateTimeScopeValue <- aggregateTimeScope (timeWindow draft) (filters draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  subjectObject <- resolveSubjectObject ontology (subject draft)
  aggregateDimensions <- resolveAggregateDimensions ontology subjectObject (dimensions draft)
  grounded <-
    resolveAggregateGrounding
      ontology
      draft
      rawMeasure
      subjectObject
      aggregateDimensions
      aggregateTimeScopeValue
      limitValue
  pure (aggregateQuery grounded)

resolveAggregateDimensions :: Ontology -> Object -> [Text] -> Either Text [SemanticGroupingDimension]
resolveAggregateDimensions ontology subjectObject rawDimensions =
  -- Aggregates can group by one or more public ontology attributes. If the user
  -- only names a subject, group by that subject's identity dimension.
  resolveDefaultGroupingDimensions ontology subjectObject rawDimensions

resolveAggregateGrounding :: Ontology -> SemanticDraft -> Text -> Object -> [SemanticGroupingDimension] -> TimeScope -> Maybe Int -> Either Text GroundedAggregate
resolveAggregateGrounding ontology draft rawMeasure subjectObject aggregateDimensions aggregateTimeScopeValue maybeLimit =
  -- Search ontology fact objects for one that can produce the requested
  -- aggregate metric by the requested public grouping dimensions.
  selectMetricFactGrounding
    failureMessage
    ontology
    rawMeasure
    (draftMeasurePhrases draft)
    aggregateCandidateEligibility
    groundAggregateFactCandidateValue
  where
    failureMessage =
      "Could not ground aggregate draft with subject '"
        <> subject draft
        <> "', measure '"
        <> rawMeasure
        <> "', and the requested grouping/filter shape against executable ontology metrics."
    aggregateCandidateEligibility factObjectValue = do
      mapM_ (requireGroupingDimensionReachable ontology factObjectValue . groupingDimensionName) aggregateDimensions
      _ <- requireTimeScopeFactSurface aggregateTimeScopeValue factObjectValue
      let groupObjects = map groupingDimensionObject aggregateDimensions
      pure
        ( maximum
            (subjectFactAffinity subjectObject factObjectValue : map (`subjectFactAffinity` factObjectValue) groupObjects)
        )
    groundAggregateFactCandidateValue =
      groundAggregateFactCandidate ontology draft aggregateDimensions aggregateTimeScopeValue maybeLimit

groundAggregateFactCandidate :: Ontology -> SemanticDraft -> [SemanticGroupingDimension] -> TimeScope -> Maybe Int -> MetricFactCandidate -> Maybe GroundedAggregate
groundAggregateFactCandidate ontology draft aggregateDimensions aggregateTimeScopeValue maybeLimit candidate = do
  rowPredicateTree <- groundDraftRowPredicate ontology factObjectValue (filters draft) (predicate draft)
  resultPredicateTree <- groundDraftResultPredicate factObjectValue metricValue (resultFilters draft) (resultPredicate draft)
  let groupObjects = map groupingDimensionObject aggregateDimensions
  pure
    GroundedAggregate
      { aggregateFactObject = factObjectValue
      , aggregateGroupObjects = groupObjects
      , aggregateMetricDef = metricValue
      , aggregateMetricDefs = metricValues
      , aggregateDisplayDimensions = map groupingDimensionName aggregateDimensions
      , aggregateFilterValues = timeScopeFilters aggregateTimeScopeValue
      , aggregateRowPredicateValue = rowPredicateTree
      , aggregateResultPredicateValue = resultPredicateTree
      , aggregateLimitValue = maybeLimit
      , aggregateAssumptions = assumptions draft
      , aggregateMatchScore = candidateMatchScore candidate
      , aggregateSubjectAffinityScore = candidateAffinityScore candidate
      }
  where
    factObjectValue = candidateFactObject candidate
    metricValue = candidateMetricDef candidate
    metricValues = candidateMetricDefs candidate

aggregateQuery :: GroundedAggregate -> QI.Query
aggregateQuery grounded =
  -- Build typed Query IR for a grouped aggregate metric query.
  -- No order/limit is added here because aggregate output is a summary table,
  -- not a ranked leaderboard.
  QI.MetricQuery
    QI.MetricQuerySpec
      { QI.sharedQuery =
          QI.BaseQuery
            { QI.coreFactObject = objectName (aggregateFactObject grounded)
            , QI.metrics = map metricName (aggregateMetricDefs grounded)
            , QI.dimensions = aggregateDisplayDimensions grounded
            , QI.timeGrain = Nothing
            , QI.filters = aggregateFilterValues grounded
            , QI.rowPredicate = aggregateRowPredicateValue grounded
            , QI.resultPredicate = aggregateResultPredicateValue grounded
            , QI.orders = []
            , QI.limit = aggregateLimitValue grounded
            , QI.assumptions = aggregateAssumptions grounded
            }
      , QI.entityFilters = []
      , QI.comparison = Nothing
      }
