{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Aggregate (semanticAggregateDraftToQuery) where

import Data.List (sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import OntologyLayer.Graph (findPath)
import OntologyLayer.Types (Ontology (objects), Object)
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.Types

semanticAggregateDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticAggregateDraftToQuery ontology draft = do
  -- Turn an aggregate draft into typed Query IR.
  -- Aggregates are grouped summaries, not disguised Top-N rankings.
  rawMeasure <- requireDraftMeasureForFamily "Aggregate" draft
  aggregateFilters <- requireRankingFilters (timeWindow draft) (filters draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  subjectObject <- resolveSubjectObject ontology (subject draft)
  aggregateDimension <- resolveAggregateDimension ontology subjectObject (dimensions draft)
  grounded <-
    resolveAggregateGrounding
      ontology
      draft
      rawMeasure
      subjectObject
      aggregateDimension
      aggregateFilters
      limitValue
  pure (aggregateQuery grounded)

resolveAggregateDimension :: Ontology -> Object -> [Text] -> Either Text AggregateDimension
resolveAggregateDimension ontology subjectObject rawDimensions =
  -- Aggregates need one public grouping dimension. If the user only names a
  -- subject, group by that subject's identity dimension.
  case rawDimensions of
    [] -> aggregateIdentityDimension subjectObject
    [rawDimension] -> resolveAggregateDimensionValue ontology subjectObject rawDimension
    _ -> Left "Aggregate drafts support exactly one business grouping dimension."

resolveAggregateDimensionValue :: Ontology -> Object -> Text -> Either Text AggregateDimension
resolveAggregateDimensionValue ontology subjectObject rawDimension
  | trendDimensionMatchesSubject subjectObject rawDimension = aggregateIdentityDimension subjectObject
  | otherwise =
      case resolveSubjectObject ontology rawDimension of
        Right dimensionObject -> aggregateIdentityDimension dimensionObject
        Left _ ->
          case bestPublicDimensionMatch rawDimension subjectObject of
            Just dimensionNameValue ->
              Right
                AggregateDimension
                  { aggregateDimensionObject = subjectObject
                  , aggregateDimensionName = dimensionNameValue
                  }
            Nothing ->
              Left
                ( "Could not ground aggregate grouping dimension '"
                    <> rawDimension
                    <> "' to a public ontology dimension."
                )

aggregateIdentityDimension :: Object -> Either Text AggregateDimension
aggregateIdentityDimension objectValue =
  maybe
    (Left ("No public identity dimension exists for aggregate grouping object '" <> objectName objectValue <> "'."))
    ( \dimensionNameValue ->
        Right
          AggregateDimension
            { aggregateDimensionObject = objectValue
            , aggregateDimensionName = dimensionNameValue
            }
    )
    (identityDimension objectValue)

resolveAggregateGrounding :: Ontology -> SemanticDraft -> Text -> Object -> AggregateDimension -> RankingFilterBundle -> Maybe Int -> Either Text GroundedAggregate
resolveAggregateGrounding ontology draft rawMeasure subjectObject aggregateDimension aggregateFilters maybeLimit =
  -- Search ontology fact objects for one that can produce the requested
  -- aggregate metric by the requested public grouping dimension.
  case rankedCandidates of
    candidate : _ -> Right candidate
    [] ->
      Left
        ( "Could not ground aggregate draft with subject '"
            <> subject draft
            <> "', measure '"
            <> rawMeasure
            <> "', and the requested grouping/filter shape against executable ontology metrics."
        )
  where
    rankedCandidates =
      sortOn aggregateCandidateRank $
        mapMaybe
          (groundAggregateFactCandidate ontology draft rawMeasure subjectObject aggregateDimension aggregateFilters maybeLimit)
          (objects ontology)

aggregateCandidateRank :: GroundedAggregate -> (Down Int, Down Int, Text)
aggregateCandidateRank candidate =
  ( Down (aggregateMatchScore candidate)
  , Down (aggregateSubjectAffinityScore candidate)
  , objectName (aggregateFactObject candidate)
  )

groundAggregateFactCandidate :: Ontology -> SemanticDraft -> Text -> Object -> AggregateDimension -> RankingFilterBundle -> Maybe Int -> Object -> Maybe GroundedAggregate
groundAggregateFactCandidate ontology draft rawMeasure subjectObject aggregateDimension aggregateFilters maybeLimit factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName (aggregateDimensionObject aggregateDimension))
  _ <- requireRankingFactSurface aggregateFilters factObjectValue
  metricValue <- bestMetricMatch rawMeasure factObjectValue
  pure
    GroundedAggregate
      { aggregateFactObject = factObjectValue
      , aggregateGroupObject = aggregateDimensionObject aggregateDimension
      , aggregateMetricDef = metricValue
      , aggregateDisplayDimension = aggregateDimensionName aggregateDimension
      , aggregateFilterValues = rankingFilterValues aggregateFilters
      , aggregateLimitValue = maybeLimit
      , aggregateAssumptions = assumptions draft
      , aggregateMatchScore = metricMatchScore rawMeasure metricValue
      , aggregateSubjectAffinityScore =
          max
            (subjectFactAffinity subjectObject factObjectValue)
            (subjectFactAffinity (aggregateDimensionObject aggregateDimension) factObjectValue)
      }

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
            , QI.metrics = [metricName (aggregateMetricDef grounded)]
            , QI.dimensions = [aggregateDisplayDimension grounded]
            , QI.timeGrain = Nothing
            , QI.filters = aggregateFilterValues grounded
            , QI.linkedFilters = []
            , QI.orders = []
            , QI.limit = aggregateLimitValue grounded
            , QI.assumptions = aggregateAssumptions grounded
            }
      , QI.entityFilters = []
      , QI.comparison = Nothing
      }
