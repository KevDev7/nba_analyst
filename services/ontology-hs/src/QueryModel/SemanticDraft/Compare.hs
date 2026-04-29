{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Compare (semanticCompareDraftToQuery) where

import Data.List (sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import OntologyLayer.Graph (findPath)
import OntologyLayer.Types (AttributeKind (Dimension), AttributeVisibility (Public), Object, Ontology (objects))
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.FilterGrounding (groundDraftRowPredicate)
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Grouping (requireGroupingDimensionReachable, resolveGroupingDimensionValue)
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.Types

semanticCompareDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticCompareDraftToQuery ontology draft = do
  -- Turn a comparison draft into typed Query IR.
  -- Python has already resolved raw names into snapshot-backed EntityRefs.
  if null (resultFilters draft) && resultPredicate draft == Nothing
    then pure ()
    else Left "Comparison result filters are not supported because comparison results are computed after SQL execution."
  rawMeasure <- requireDraftMeasureForFamily "Comparison" draft
  timeScopeValue <- comparisonTimeScope (timeWindow draft) (filters draft)
  let filtersForComparison = timeScopeFilters timeScopeValue
  resolvedEntityValues <- requireResolvedComparisonEntities draft
  subjectObject <- resolveSubjectObject ontology (subject draft)
  displayDimensionValue <- requireComparisonIdentityDimension subjectObject
  grainValue <- traverse normalizeComparisonGrain (grain draft)
  grounded <-
    resolveComparisonGrounding
      ontology
      draft
      rawMeasure
      subjectObject
      displayDimensionValue
      grainValue
      timeScopeValue
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

normalizeComparisonGrain :: Text -> Either Text Text
normalizeComparisonGrain rawGrain =
  case normalizeTrendGrain rawGrain of
    Just normalizedGrain -> Right normalizedGrain
    Nothing -> Left "Could not ground comparison grain. Supported calendar grains are day, week, month, and season."

resolveComparisonGrounding :: Ontology -> SemanticDraft -> Text -> Object -> Text -> Maybe Text -> TimeScope -> [QI.Filter] -> [QI.EntityRef] -> Either Text GroundedComparison
resolveComparisonGrounding ontology draft rawMeasure subjectObject displayDimensionValue maybeGrainValue timeScopeValue filtersForComparison entityValues =
  -- Search ontology fact objects for one that can compare the requested entities
  -- by the requested metric over the resolved TimeScope.
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
          (groundComparisonFactCandidate ontology draft rawMeasure subjectObject displayDimensionValue maybeGrainValue timeScopeValue filtersForComparison entityValues)
          (objects ontology)

comparisonCandidateRank :: GroundedComparison -> (Down Int, Down Int, Text)
comparisonCandidateRank candidate =
  ( Down (comparisonMatchScore candidate)
  , Down (comparisonSubjectAffinityScore candidate)
  , objectName (comparisonFactObject candidate)
  )

groundComparisonFactCandidate :: Ontology -> SemanticDraft -> Text -> Object -> Text -> Maybe Text -> TimeScope -> [QI.Filter] -> [QI.EntityRef] -> Object -> Maybe GroundedComparison
groundComparisonFactCandidate ontology draft rawMeasure subjectObject displayDimensionValue maybeGrainValue timeScopeValue filtersForComparison entityValues factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName subjectObject)
  _ <- requireTimeScopeFactSurface timeScopeValue factObjectValue
  metricValue <- bestMetricMatch rawMeasure factObjectValue
  rowPredicateTree <- groundDraftRowPredicate ontology factObjectValue (filters draft) (predicate draft)
  displayDimensionValues <- resolveComparisonDisplayDimensions ontology draft subjectObject displayDimensionValue maybeGrainValue factObjectValue
  pure
    GroundedComparison
      { comparisonFactObject = factObjectValue
      , comparisonSubjectObject = subjectObject
      , comparisonMetricDef = metricValue
      , comparisonDisplayDimension = displayDimensionValue
      , comparisonDisplayDimensions = displayDimensionValues
      , comparisonGrainValue = maybeGrainValue
      , comparisonFilterValues = filtersForComparison
      , comparisonRowPredicateValue = rowPredicateTree
      , comparisonEntitiesValue = entityValues
      , comparisonAssumptions = assumptions draft
      , comparisonMatchScore = metricMatchScore rawMeasure metricValue
      , comparisonSubjectAffinityScore = subjectFactAffinity subjectObject factObjectValue
      }

resolveComparisonDisplayDimensions :: Ontology -> SemanticDraft -> Object -> Text -> Maybe Text -> Object -> Maybe [Text]
resolveComparisonDisplayDimensions ontology draft subjectObject displayDimensionValue maybeGrainValue factObjectValue = do
  breakdownDimensions <- mapM resolveBreakdownDimension dimensionsToResolve
  pure (displayDimensionValue : filter (/= displayDimensionValue) breakdownDimensions)
  where
    dimensionsToResolve =
      [ rawDimension
      | rawDimension <- dimensions draft
      , not (duplicatesTimeGrain rawDimension)
      ]
    duplicatesTimeGrain rawDimension =
      case maybeGrainValue of
        Just grainValue -> normalizeTrendGrain rawDimension == Just grainValue
        Nothing -> False
    resolveBreakdownDimension rawDimension = do
      groupingDimension <- either (const Nothing) Just (resolveGroupingDimensionValue ontology subjectObject rawDimension)
      let dimensionNameValue = groupingDimensionName groupingDimension
      _ <- requireGroupingDimensionReachable ontology factObjectValue dimensionNameValue
      pure dimensionNameValue

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
            , QI.dimensions = comparisonDisplayDimensions grounded
            , QI.timeGrain = QI.TimeGrainRef <$> comparisonGrainValue grounded
            , QI.filters = comparisonFilterValues grounded
            , QI.rowPredicate = comparisonRowPredicateValue grounded
            , QI.resultPredicate = Nothing
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
