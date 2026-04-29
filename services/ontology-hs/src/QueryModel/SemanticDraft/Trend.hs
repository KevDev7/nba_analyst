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
import QueryModel.SemanticDraft.FilterGrounding (groundDraftRowPredicate)
import QueryModel.SemanticDraft.Filters
import QueryModel.SemanticDraft.Grouping (requireGroupingDimensionReachable, resolveGroupingDimensionValue)
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.ResultFilterGrounding (groundDraftResultPredicate)
import QueryModel.SemanticDraft.Types

semanticTrendDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticTrendDraftToQuery ontology draft = do
  -- Turn a trend draft into typed Query IR without assuming a specific table.
  -- Calendar grains are grounded through ontology-backed date/season attributes.
  rawMeasure <- requireDraftMeasureForFamily "Trend" draft
  trendGrain <- requireTrendGrain draft
  trendTimeScopeValue <- trendTimeScope trendGrain (timeWindow draft) (filters draft)
  let filtersForTrend = timeScopeFilters trendTimeScopeValue
  subjectObject <- resolveSubjectObject ontology (subject draft)
  trendDimensions <- resolveTrendDimensions ontology subjectObject (dimensions draft)
  grounded <- resolveTrendGrounding ontology draft rawMeasure subjectObject trendDimensions trendGrain trendTimeScopeValue filtersForTrend
  pure (trendQuery grounded)

resolveTrendDimensions :: Ontology -> Object -> [Text] -> Either Text [SemanticGroupingDimension]
resolveTrendDimensions ontology subjectObject rawDimensions =
  -- A trend may be one overall series or one series per business object.
  -- Example: dimensions ["team"] grounds to Team.team_name.
  mapM (resolveGroupingDimensionValue ontology subjectObject) rawDimensions

resolveTrendGrounding :: Ontology -> SemanticDraft -> Text -> Object -> [SemanticGroupingDimension] -> Text -> TimeScope -> [QI.Filter] -> Either Text GroundedTrend
resolveTrendGrounding ontology draft rawMeasure subjectObject trendDimensions trendGrain trendTimeScopeValue filtersForTrend =
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
          (groundTrendFactCandidate ontology draft rawMeasure subjectObject trendDimensions trendGrain trendTimeScopeValue filtersForTrend)
          (objects ontology)

trendCandidateRank :: GroundedTrend -> (Down Int, Down Int, Text)
trendCandidateRank candidate =
  ( Down (trendMatchScore candidate)
  , Down (trendSubjectAffinityScore candidate)
  , objectName (trendFactObject candidate)
  )

groundTrendFactCandidate :: Ontology -> SemanticDraft -> Text -> Object -> [SemanticGroupingDimension] -> Text -> TimeScope -> [QI.Filter] -> Object -> Maybe GroundedTrend
groundTrendFactCandidate ontology draft rawMeasure subjectObject trendDimensions trendGrain trendTimeScopeValue filtersForTrend factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName subjectObject)
  _ <- requireTrendFactSurface trendGrain trendTimeScopeValue factObjectValue
  metricValue <- bestMetricMatch rawMeasure factObjectValue
  metricValues <- mapM (`bestMetricMatch` factObjectValue) (draftMeasurePhrases draft)
  mapM_ (requireGroupingDimensionReachable ontology factObjectValue . groupingDimensionName) trendDimensions
  let predicateDraftFilters = filter (not . draftFilterIsTimeScopeFilter) (filters draft)
  rowPredicateTree <- groundDraftRowPredicate ontology factObjectValue predicateDraftFilters (predicate draft)
  resultPredicateTree <- groundDraftResultPredicate factObjectValue metricValue (resultFilters draft) (resultPredicate draft)
  let trendDimensionObjects = map groupingDimensionObject trendDimensions
  pure
    GroundedTrend
      { trendFactObject = factObjectValue
      , trendMetricDef = metricValue
      , trendMetricDefs = metricValues
      , trendDisplayDimensions = map groupingDimensionName trendDimensions
      , trendGrainValue = trendGrain
      , trendFilterValues = filtersForTrend
      , trendRowPredicateValue = rowPredicateTree
      , trendResultPredicateValue = resultPredicateTree
      , trendAssumptions = assumptions draft
      , trendMatchScore = metricMatchScore rawMeasure metricValue
      , trendSubjectAffinityScore =
          maximum
            (trendFactAffinity trendGrain subjectObject factObjectValue : map (`subjectFactAffinity` factObjectValue) trendDimensionObjects)
      }

requireTrendFactSurface :: Text -> TimeScope -> Object -> Maybe ()
requireTrendFactSurface trendGrain trendTimeScopeValue factObjectValue = do
  case trendGrain of
    "day" -> requireFactDate
    "week" -> requireFactDate
    "month" -> requireFactDate
    "season" -> do
      _ <- findAttribute factObjectValue "season_year"
      Just ()
    _ -> Nothing
  case trendTimeScopeValue of
    RecentGames _ _ -> Nothing
    LastNDays _ -> requireFactDate
    PastYear -> requireFactDate
    DateRange _ _ -> requireFactDate
    ExactSeason _ _ -> requireFactSeason
    SeasonTypeOnly _ -> requireFactSeasonType
    AllAvailable -> Just ()
  where
    requireFactDate = do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    requireFactSeason = do
      _ <- findAttribute factObjectValue "season_year"
      _ <- findAttribute factObjectValue "season_type"
      Just ()
    requireFactSeasonType = do
      _ <- findAttribute factObjectValue "season_type"
      Just ()

trendQuery :: GroundedTrend -> QI.Query
trendQuery grounded =
  -- Build typed Query IR for a time-series metric query.
  QI.MetricQuery
    QI.MetricQuerySpec
      { QI.sharedQuery =
          QI.BaseQuery
            { QI.coreFactObject = objectName (trendFactObject grounded)
            , QI.metrics = map metricName (trendMetricDefs grounded)
            , QI.dimensions = trendDisplayDimensions grounded
            , QI.timeGrain = Just (QI.TimeGrainRef (trendGrainValue grounded))
            , QI.filters = trendFilterValues grounded
            , QI.rowPredicate = trendRowPredicateValue grounded
            , QI.resultPredicate = trendResultPredicateValue grounded
            , QI.orders = []
            , QI.limit = Nothing
            , QI.assumptions = trendAssumptions grounded
            }
      , QI.entityFilters = []
      , QI.comparison = Nothing
      }
