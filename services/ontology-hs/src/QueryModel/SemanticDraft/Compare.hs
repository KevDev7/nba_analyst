{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Compare (semanticCompareDraftToQuery) where

import Data.List (sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (AttributeKind (Dimension), AttributeVisibility (Public), Object, Ontology (objects))
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.FilterGrounding (groundDraftLinkedFilters)
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.Types

semanticCompareDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticCompareDraftToQuery ontology draft = do
  -- Turn a comparison draft into typed Query IR.
  -- Python has already resolved raw names into snapshot-backed EntityRefs.
  rawMeasure <- requireDraftMeasureForFamily "Comparison" draft
  filtersForComparison <- requireComparisonFilters (timeWindow draft) (filters draft)
  resolvedEntityValues <- requireResolvedComparisonEntities draft
  subjectObject <- resolveSubjectObject ontology (subject draft)
  displayDimensionValue <- requireComparisonIdentityDimension subjectObject
  grounded <-
    resolveComparisonGrounding
      ontology
      draft
      rawMeasure
      subjectObject
      displayDimensionValue
      filtersForComparison
      resolvedEntityValues
  pure (comparisonQuery grounded)

requireComparisonIdentityDimension :: Object -> Either Text Text
requireComparisonIdentityDimension objectValue =
  case comparisonDimensions of
    attributeValue : _ -> Right (attributeName attributeValue)
    [] ->
      Left
        ( "No public comparison identity dimension exists for comparison subject '"
            <> objectName objectValue
            <> "'."
        )
  where
    comparisonDimensions =
      [ attributeValue
      | attributeValue <- objectAttributes objectValue
      , attributeKind attributeValue == Dimension
      , attributeVisibility attributeValue == Public
      , OT.comparison_identity attributeValue
      ]

resolveComparisonGrounding :: Ontology -> SemanticDraft -> Text -> Object -> Text -> [QI.Filter] -> [QI.EntityRef] -> Either Text GroundedComparison
resolveComparisonGrounding ontology draft rawMeasure subjectObject displayDimensionValue filtersForComparison entityValues =
  -- Search ontology fact objects for one that can compare the requested entities
  -- by the requested metric over a recent-games window.
  case rankedCandidates of
    candidate : _ -> Right candidate
    [] ->
      Left
        ( "Could not ground comparison draft with subject '"
            <> subject draft
            <> "', measure '"
            <> rawMeasure
            <> "', and the requested comparison filters against executable ontology metrics."
        )
  where
    rankedCandidates =
      sortOn comparisonCandidateRank $
        mapMaybe
          (groundComparisonFactCandidate ontology draft rawMeasure subjectObject displayDimensionValue filtersForComparison entityValues)
          (objects ontology)

comparisonCandidateRank :: GroundedComparison -> (Down Int, Down Int, Text)
comparisonCandidateRank candidate =
  ( Down (comparisonMatchScore candidate)
  , Down (comparisonSubjectAffinityScore candidate)
  , objectName (comparisonFactObject candidate)
  )

groundComparisonFactCandidate :: Ontology -> SemanticDraft -> Text -> Object -> Text -> [QI.Filter] -> [QI.EntityRef] -> Object -> Maybe GroundedComparison
groundComparisonFactCandidate ontology draft rawMeasure subjectObject displayDimensionValue filtersForComparison entityValues factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName subjectObject)
  _ <- requireComparisonFactSurface filtersForComparison factObjectValue
  metricValue <- bestMetricMatch rawMeasure factObjectValue
  linkedFilterValue <- groundDraftLinkedFilters ontology factObjectValue (filters draft)
  pure
    GroundedComparison
      { comparisonFactObject = factObjectValue
      , comparisonSubjectObject = subjectObject
      , comparisonMetricDef = metricValue
      , comparisonDisplayDimension = displayDimensionValue
      , comparisonFilterValues = filtersForComparison
      , comparisonLinkedFilterValues = linkedFilterValue
      , comparisonEntitiesValue = entityValues
      , comparisonAssumptions = assumptions draft
      , comparisonMatchScore = metricMatchScore rawMeasure metricValue
      , comparisonSubjectAffinityScore = subjectFactAffinity subjectObject factObjectValue
      }

requireComparisonFactSurface :: [QI.Filter] -> Object -> Maybe ()
requireComparisonFactSurface filtersForComparison factObjectValue = do
  if any isLastNGamesFilter filtersForComparison
    then do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    else Nothing
  where
    isLastNGamesFilter filterValue = QI.filterKindText filterValue == "last_n_games"

comparisonQuery :: GroundedComparison -> QI.Query
comparisonQuery grounded =
  -- Build typed Query IR for a comparison across grounded entities.
  -- The comparison intent carries snapshot-backed entity IDs into planning.
  QI.MetricQuery
    QI.MetricQuerySpec
      { QI.sharedQuery =
          QI.BaseQuery
            { QI.coreFactObject = objectName (comparisonFactObject grounded)
            , QI.metrics = [metricName (comparisonMetricDef grounded)]
            , QI.dimensions = [comparisonDisplayDimension grounded]
            , QI.timeGrain = Nothing
            , QI.filters = comparisonFilterValues grounded
            , QI.linkedFilters = comparisonLinkedFilterValues grounded
            , QI.orders = []
            , QI.limit = Nothing
            , QI.assumptions = comparisonAssumptions grounded
            }
      , QI.entityFilters = []
      , QI.comparison =
          Just
            ( QI.CompareEntities
                (objectName (comparisonSubjectObject grounded))
                (comparisonEntitiesValue grounded)
            )
      }
