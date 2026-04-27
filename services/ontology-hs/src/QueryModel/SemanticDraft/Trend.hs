{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Trend (semanticTrendDraftToQuery) where

import Data.List (sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (Ontology (objects), Object)
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.Types

semanticTrendDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticTrendDraftToQuery ontology draft = do
  -- Turn a trend draft into typed Query IR without assuming a specific table.
  -- Calendar grains are grounded through ontology-backed date/season attributes.
  rawMeasure <- requireDraftMeasureForFamily "Trend" draft
  trendGrain <- requireTrendGrain draft
  filtersForTrend <- requireTrendFilters trendGrain (timeWindow draft) (filters draft)
  subjectObject <- resolveSubjectObject ontology (subject draft)
  maybeDimension <- resolveTrendDimension ontology subjectObject (dimensions draft)
  grounded <- resolveTrendGrounding ontology draft rawMeasure subjectObject maybeDimension trendGrain filtersForTrend
  pure (trendQuery grounded)

resolveTrendDimension :: Ontology -> Object -> [Text] -> Either Text (Maybe Text)
resolveTrendDimension ontology subjectObject rawDimensions =
  -- A trend may be one overall series or one series per business object.
  -- Example: dimensions ["team"] grounds to Team.team_name.
  case rawDimensions of
    [] -> Right Nothing
    [rawDimension] -> Just <$> resolveTrendDimensionValue ontology subjectObject rawDimension
    _ -> Left "Trend drafts support at most one grouping dimension."

resolveTrendDimensionValue :: Ontology -> Object -> Text -> Either Text Text
resolveTrendDimensionValue ontology subjectObject rawDimension
  | trendDimensionMatchesSubject subjectObject rawDimension =
      maybe
        (Left ("No public identity dimension exists for trend subject '" <> objectName subjectObject <> "'."))
        Right
        (identityDimension subjectObject)
  | otherwise = do
      dimensionObject <- resolveSubjectObject ontology rawDimension
      maybe
        (Left ("No public identity dimension exists for trend grouping '" <> rawDimension <> "'."))
        Right
        (identityDimension dimensionObject)

resolveTrendGrounding :: Ontology -> SemanticDraft -> Text -> Object -> Maybe Text -> Text -> [QI.Filter] -> Either Text GroundedTrend
resolveTrendGrounding ontology draft rawMeasure subjectObject maybeDimension trendGrain filtersForTrend =
  -- Search ontology fact objects for one that can produce the requested
  -- metric over the requested calendar grain.
  case rankedCandidates of
    candidate : _ -> Right candidate
    [] ->
      Left
        ( "Could not ground trend draft with subject '"
            <> subject draft
            <> "', measure '"
            <> rawMeasure
            <> "', grain '"
            <> trendGrain
            <> "', and the requested trend filters against executable ontology metrics."
        )
  where
    rankedCandidates =
      sortOn trendCandidateRank $
        mapMaybe
          (groundTrendFactCandidate ontology draft rawMeasure subjectObject maybeDimension trendGrain filtersForTrend)
          (objects ontology)

trendCandidateRank :: GroundedTrend -> (Down Int, Down Int, Text)
trendCandidateRank candidate =
  ( Down (trendMatchScore candidate)
  , Down (trendSubjectAffinityScore candidate)
  , objectName (trendFactObject candidate)
  )

groundTrendFactCandidate :: Ontology -> SemanticDraft -> Text -> Object -> Maybe Text -> Text -> [QI.Filter] -> Object -> Maybe GroundedTrend
groundTrendFactCandidate ontology draft rawMeasure subjectObject maybeDimension trendGrain filtersForTrend factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName subjectObject)
  _ <- requireTrendFactSurface trendGrain filtersForTrend factObjectValue
  metricValue <- bestMetricMatch rawMeasure factObjectValue
  _ <- requireTrendDimensionReachable ontology factObjectValue maybeDimension
  pure
    GroundedTrend
      { trendFactObject = factObjectValue
      , trendMetricDef = metricValue
      , trendDisplayDimension = maybeDimension
      , trendGrainValue = trendGrain
      , trendFilterValues = filtersForTrend
      , trendAssumptions = assumptions draft
      , trendMatchScore = metricMatchScore rawMeasure metricValue
      , trendSubjectAffinityScore = trendFactAffinity trendGrain subjectObject factObjectValue
      }

requireTrendFactSurface :: Text -> [QI.Filter] -> Object -> Maybe ()
requireTrendFactSurface trendGrain filtersForTrend factObjectValue = do
  case trendGrain of
    "day" -> requireFactDate
    "week" -> requireFactDate
    "month" -> requireFactDate
    "season" -> do
      _ <- findAttribute factObjectValue "season_year"
      Just ()
    _ -> Nothing
  if any isPastYearFilter filtersForTrend
    then requireFactDate
    else Just ()
  if any isSeasonTypeFilter filtersForTrend
    then do
      _ <- findAttribute factObjectValue "season_type"
      Just ()
    else Just ()
  where
    requireFactDate = do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    isPastYearFilter filterValue = QI.filterKindText filterValue == "past_year"
    isSeasonTypeFilter filterValue = QI.filterKindText filterValue == "season_type"

requireTrendDimensionReachable :: Ontology -> Object -> Maybe Text -> Maybe ()
requireTrendDimensionReachable _ontology _factObjectValue Nothing = Just ()
requireTrendDimensionReachable ontology factObjectValue (Just dimensionValue) = do
  case
    [ ()
    | candidateObject <- objects ontology
    , findAttribute candidateObject dimensionValue /= Nothing
    , findPath ontology 2 (objectName factObjectValue) (objectName candidateObject) /= Nothing
    ]
    of
    _ : _ -> Just ()
    [] ->
      case findAttribute factObjectValue dimensionValue of
        Just _ -> Just ()
        Nothing -> Nothing

trendQuery :: GroundedTrend -> QI.Query
trendQuery grounded =
  -- Build typed Query IR for a time-series metric query.
  QI.MetricQuery
    QI.MetricQuerySpec
      { QI.sharedQuery =
          QI.BaseQuery
            { QI.coreFactObject = objectName (trendFactObject grounded)
            , QI.metrics = [metricName (trendMetricDef grounded)]
            , QI.dimensions = maybe [] pure (trendDisplayDimension grounded)
            , QI.timeGrain = Just (QI.TimeGrainRef (trendGrainValue grounded))
            , QI.filters = trendFilterValues grounded
            , QI.linkedFilters = []
            , QI.orders = []
            , QI.limit = Nothing
            , QI.assumptions = trendAssumptions grounded
            }
      , QI.entityFilters = []
      , QI.comparison = Nothing
      }
