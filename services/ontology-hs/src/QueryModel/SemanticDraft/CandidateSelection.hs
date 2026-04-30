{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.CandidateSelection
  ( MetricFactCandidate
  , candidateAffinityScore
  , candidateFactObject
  , candidateMatchScore
  , candidateMetricDef
  , candidateMetricDefs
  , selectMetricFactGrounding
  ) where

import Data.List (sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import OntologyLayer.Types (Object, Ontology (objects))
import qualified OntologyLayer.Types as OT
import QueryModel.SemanticDraft.Match

data MetricFactCandidate = MetricFactCandidate
  -- A fact object that passed a family-specific eligibility check and has the
  -- ontology metrics needed for the draft.
  { candidateFactObject :: Object
  , candidateMetricDef :: OT.MetricDef
  , candidateMetricDefs :: [OT.MetricDef]
  , candidateMatchScore :: Int
  , candidateAffinityScore :: Int
  }

selectMetricFactGrounding ::
  Text ->
  Ontology ->
  Text ->
  [Text] ->
  (Object -> Maybe Int) ->
  (MetricFactCandidate -> Maybe grounded) ->
  Either Text grounded
selectMetricFactGrounding failureMessage ontology rawMeasure rawMeasurePhrases factEligibilityScore groundCandidate =
  case mapMaybe groundCandidate (rankMetricFactCandidates ontology rawMeasure rawMeasurePhrases factEligibilityScore) of
    candidateValue : _ -> Right candidateValue
    [] -> Left failureMessage

rankMetricFactCandidates ::
  Ontology ->
  Text ->
  [Text] ->
  (Object -> Maybe Int) ->
  [MetricFactCandidate]
rankMetricFactCandidates ontology rawMeasure rawMeasurePhrases factEligibilityScore =
  -- Shared mechanics only: walk fact objects, ask the family whether a fact is
  -- eligible, ground metrics, then rank. Each family still owns its policy.
  sortOn candidateRank $
    mapMaybe groundFactCandidate (objects ontology)
  where
    groundFactCandidate factObjectValue = do
      affinityScoreValue <- factEligibilityScore factObjectValue
      metricValue <- bestMetricMatch rawMeasure factObjectValue
      metricValues <- mapM (`bestMetricMatch` factObjectValue) rawMeasurePhrases
      pure
        MetricFactCandidate
          { candidateFactObject = factObjectValue
          , candidateMetricDef = metricValue
          , candidateMetricDefs = metricValues
          , candidateMatchScore = metricMatchScore rawMeasure metricValue
          , candidateAffinityScore = affinityScoreValue
          }
    candidateRank candidate =
      ( Down (candidateMatchScore candidate)
      , Down (candidateAffinityScore candidate)
      , objectName (candidateFactObject candidate)
      )
