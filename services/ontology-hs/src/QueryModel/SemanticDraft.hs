-- Purpose:
-- Normalize an LLM-produced semantic draft into typed Query IR through ontology grounding.
--
-- Uses:
-- - a deliberately loose, language-facing JSON draft
-- - ontology objects, links, public dimensions, and executable metrics
--
-- Produces:
-- - QueryModel.IR.Query for grounded planning
--
-- Next:
-- - GroundedPlanning.Validation

{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft
  ( SemanticDraft
  , semanticDraftToQuery
  ) where

import Control.Applicative ((<|>))
import Data.Aeson (FromJSON (parseJSON), withObject, (.:), (.:?), (.!=))
import Data.Char (isAlphaNum)
import Data.List (nub, sortOn)
import Data.Maybe (mapMaybe)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types
  ( AttributeKind (Dimension)
  , AttributeVisibility (Public)
  , Object
  , Ontology (objects)
  )
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI

data DraftTimeWindow = DraftTimeWindow
  -- The time_window object from the LLM draft.
  -- Example: {"kind":"last_n_games","value":10}.
  { kind :: Text
  , value :: Maybe QI.FilterValue
  }
  deriving (Show, Eq)

instance FromJSON DraftTimeWindow where
  parseJSON = withObject "DraftTimeWindow" $ \obj ->
    DraftTimeWindow
      <$> obj .: "kind"
      <*> obj .:? "value"

data SemanticDraft = SemanticDraft
  -- Haskell's version of the loose JSON draft Python received from the LLM.
  -- These fields stay user-facing; they are not ontology/table/SQL keys yet.
  { task :: Text
  , subject :: Text
  , measure :: Maybe Text
  , measures :: [Text]
  , dimensions :: [Text]
  , filters :: [DraftFilter]
  , timeWindow :: DraftTimeWindow
  , grain :: Maybe Text
  , order :: [DraftFreeformObject]
  , limit :: Maybe Int
  , sort :: Maybe Text
  , entities :: [Text]
  , resolvedEntities :: [QI.EntityRef]
  , operations :: [DraftFreeformObject]
  , assumptions :: [Text]
  }
  deriving (Show, Eq)

newtype DraftFreeformObject = DraftFreeformObject ()
  deriving (Show, Eq)

instance FromJSON DraftFreeformObject where
  parseJSON = withObject "DraftFreeformObject" $ \_obj -> pure (DraftFreeformObject ())

data DraftFilter = DraftFilter
  -- A loose user-facing filter captured by the LLM.
  -- Example: {"field":"season type","op":"=","value":"regular season"}.
  { filterField :: Maybe Text
  , filterOp :: Maybe Text
  , filterValue :: Maybe QI.FilterValue
  }
  deriving (Show, Eq)

instance FromJSON DraftFilter where
  parseJSON = withObject "DraftFilter" $ \obj ->
    DraftFilter
      <$> obj .:? "field"
      <*> obj .:? "op"
      <*> obj .:? "value"

instance FromJSON SemanticDraft where
  parseJSON = withObject "SemanticDraft" $ \obj ->
    SemanticDraft
      <$> obj .: "task"
      <*> obj .: "subject"
      <*> obj .:? "measure"
      <*> obj .:? "measures" .!= []
      <*> obj .:? "dimensions" .!= []
      <*> obj .:? "filters" .!= []
      <*> obj .: "time_window"
      <*> obj .:? "grain"
      <*> obj .:? "order" .!= []
      <*> obj .:? "limit"
      <*> obj .:? "sort"
      <*> obj .:? "entities" .!= []
      <*> obj .:? "resolved_entities" .!= []
      <*> obj .:? "operations" .!= []
      <*> obj .:? "assumptions" .!= []

data GroundedRanking = GroundedRanking
  -- A ranking draft after it has been grounded against the ontology.
  -- At this point we know the real fact object, subject object, metric, and
  -- display dimension needed to build typed Query IR.
  { factObject :: Object
  , subjectObject :: Object
  , metricDef :: OT.MetricDef
  , displayDimension :: Text
  , filterValues :: [QI.Filter]
  , limitValue :: Maybe Int
  , assumptionValues :: [Text]
  , matchScore :: Int
  , subjectAffinityScore :: Int
  }

data RankingFilterBundle
  = RecentRanking Int
  | SeasonRanking Text Text
  deriving (Show, Eq)

data GroundedTrend = GroundedTrend
  -- A trend draft after ontology grounding.
  -- It identifies the fact surface, metric, optional series dimension, grain,
  -- and filters needed to build a typed time-series Query IR.
  { trendFactObject :: Object
  , trendMetricDef :: OT.MetricDef
  , trendDisplayDimension :: Maybe Text
  , trendGrainValue :: Text
  , trendFilterValues :: [QI.Filter]
  , trendAssumptions :: [Text]
  , trendMatchScore :: Int
  , trendSubjectAffinityScore :: Int
  }

data GroundedComparison = GroundedComparison
  -- A comparison draft after data-backed entity names have been grounded and
  -- the ontology has selected a fact object, metric, and identity dimension.
  { comparisonFactObject :: Object
  , comparisonSubjectObject :: Object
  , comparisonMetricDef :: OT.MetricDef
  , comparisonDisplayDimension :: Text
  , comparisonFilterValues :: [QI.Filter]
  , comparisonEntitiesValue :: [QI.EntityRef]
  , comparisonAssumptions :: [Text]
  , comparisonMatchScore :: Int
  , comparisonSubjectAffinityScore :: Int
  }

data AggregateDimension = AggregateDimension
  { aggregateDimensionObject :: Object
  , aggregateDimensionName :: Text
  }

data GroundedAggregate = GroundedAggregate
  -- An aggregate draft after ontology grounding.
  -- It identifies the fact surface, metric, and public grouping dimension
  -- needed to build grouped metric-query IR without adding a ranking shape.
  { aggregateFactObject :: Object
  , aggregateGroupObject :: Object
  , aggregateMetricDef :: OT.MetricDef
  , aggregateDisplayDimension :: Text
  , aggregateFilterValues :: [QI.Filter]
  , aggregateLimitValue :: Maybe Int
  , aggregateAssumptions :: [Text]
  , aggregateMatchScore :: Int
  , aggregateSubjectAffinityScore :: Int
  }

data GroundedFind = GroundedFind
  { findFactObject :: Object
  , findTargetObject :: Object
  , findDisplayDimensions :: [Text]
  , findPredicateValues :: [QI.FindPredicate]
  , findFilterValues :: [QI.Filter]
  , findLimitValue :: Maybe Int
  , findAssumptions :: [Text]
  , findMatchScore :: Int
  }

semanticDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticDraftToQuery ontology draft = do
  -- Look at the question family captured by the LLM draft.
  -- Implemented families are normalized through ontology grounding here.
  case draftTask (task draft) of
    DraftRank -> semanticRankDraftToQuery ontology draft
    DraftTrend -> semanticTrendDraftToQuery ontology draft
    DraftAggregate -> semanticAggregateDraftToQuery ontology draft
    DraftFind -> semanticFindDraftToQuery ontology draft
    DraftCompare -> semanticCompareDraftToQuery ontology draft
    DraftUnknown rawTask ->
      Left
        ( "Unknown semantic draft task '"
            <> rawTask
            <> "'. Expected one of rank, trend, aggregate, find, or compare."
        )

data DraftTask
  = DraftRank
  | DraftTrend
  | DraftAggregate
  | DraftFind
  | DraftCompare
  | DraftUnknown Text
  deriving (Show, Eq)

draftTask :: Text -> DraftTask
draftTask rawTask =
  -- Normalize task words like "top" or "leaders" into broad question families.
  case normalizedKey rawTask of
    "rank" -> DraftRank
    "ranking" -> DraftRank
    "top" -> DraftRank
    "leaderboard" -> DraftRank
    "leaders" -> DraftRank
    "trend" -> DraftTrend
    "timeseries" -> DraftTrend
    "aggregate" -> DraftAggregate
    "aggregation" -> DraftAggregate
    "calculate" -> DraftAggregate
    "find" -> DraftFind
    "lookup" -> DraftFind
    "explore" -> DraftFind
    "compare" -> DraftCompare
    "comparison" -> DraftCompare
    _ -> DraftUnknown rawTask

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

semanticFindDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticFindDraftToQuery ontology draft = do
  -- Turn a find draft into typed Query IR for row retrieval.
  -- The fact object is selected by ontology paths and filter support.
  targetObject <- resolveSubjectObject ontology (subject draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  requireFindFilters (filters draft)
  findTimeFilters <- findWindowFilters (timeWindow draft) (filters draft)
  grounded <- resolveFindGrounding ontology draft targetObject findTimeFilters limitValue
  pure (findQuery grounded)

semanticCompareDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticCompareDraftToQuery ontology draft = do
  -- Turn a comparison draft into typed Query IR.
  -- Python has already resolved raw names into snapshot-backed EntityRefs.
  rawMeasure <- requireDraftMeasureForFamily "Comparison" draft
  filtersForComparison <- requireComparisonFilters (timeWindow draft)
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

requireDraftMeasure :: SemanticDraft -> Either Text Text
requireDraftMeasure draft =
  -- Ranking needs one measure phrase, like "points", "scoring", or "average points".
  requireDraftMeasureForFamily "Ranking" draft

requireDraftMeasureForFamily :: Text -> SemanticDraft -> Either Text Text
requireDraftMeasureForFamily familyName draft =
  case measure draft of
    Just rawMeasure | T.strip rawMeasure /= "" -> Right rawMeasure
    _ ->
      case measures draft of
        rawMeasure : _ | T.strip rawMeasure /= "" -> Right rawMeasure
        _ -> Left (familyName <> " drafts require at least one user-facing measure phrase.")

requireFindFilters :: [DraftFilter] -> Either Text ()
requireFindFilters draftFilters =
  case draftFilters of
    [] -> Left "Find drafts require at least one user-facing filter."
    _ -> pure ()

requireTrendGrain :: SemanticDraft -> Either Text Text
requireTrendGrain draft =
  -- Normalize user-facing calendar grain words. Custom interval buckets are
  -- intentionally out of scope until the product defines an anchor policy.
  case normalizeTrendGrain =<< (grain draft <|> Just (kind (timeWindow draft))) of
    Just trendGrain -> Right trendGrain
    Nothing ->
      Left "Could not ground trend grain. Supported calendar grains are day, week, month, and season."

normalizeTrendGrain :: Text -> Maybe Text
normalizeTrendGrain rawGrain =
  case normalizedKey rawGrain of
    "day" -> Just "day"
    "daily" -> Just "day"
    "date" -> Just "day"
    "game" -> Just "day"
    "week" -> Just "week"
    "weekly" -> Just "week"
    "calendarweek" -> Just "week"
    "month" -> Just "month"
    "monthly" -> Just "month"
    "calendarmonth" -> Just "month"
    "season" -> Just "season"
    "seasonal" -> Just "season"
    _ -> Nothing

requireTrendFilters :: Text -> DraftTimeWindow -> [DraftFilter] -> Either Text [QI.Filter]
requireTrendFilters trendGrain window draftFilters = do
  timeFilters <- trendWindowFilters trendGrain window
  pure (timeFilters <> trendSeasonTypeFilters draftFilters)

trendWindowFilters :: Text -> DraftTimeWindow -> Either Text [QI.Filter]
trendWindowFilters trendGrain window =
  case normalizedKey (kind window) of
    "pastyear" -> Right [QI.pastYearFilter]
    "all" -> Right []
    "none" -> Right []
    "unspecified" -> Right []
    "season"
      | trendGrain == "season" -> Right []
    grainKey
      | normalizeTrendGrain grainKey == Just trendGrain -> Right []
    _ -> Left ("Could not ground trend time window '" <> kind window <> "' against ontology-backed trend filters.")

trendSeasonTypeFilters :: [DraftFilter] -> [QI.Filter]
trendSeasonTypeFilters draftFilters =
  case seasonTypeFromFilters draftFilters of
    Just seasonTypeLabel -> [QI.seasonTypeFilter seasonTypeLabel]
    Nothing -> []

findWindowFilters :: DraftTimeWindow -> [DraftFilter] -> Either Text [QI.Filter]
findWindowFilters window draftFilters =
  -- Preserve find-query time intent as planner filters instead of silently
  -- dropping it. Validation/compilation later proves the fact surface can run it.
  case (normalizedKey (kind window), value window) of
    ("all", _) -> Right []
    ("none", _) -> Right []
    ("unspecified", _) -> Right []
    ("lastngames", Just (QI.FilterInt gamesValue))
      | gamesValue > 0 -> Right [QI.lastNGamesFilter gamesValue]
    ("pastyear", _) -> Right [QI.pastYearFilter]
    ("season", Just (QI.FilterText seasonLabel)) -> do
      seasonTypeLabel <- requireSeasonType window draftFilters
      Right [QI.exactSeasonFilter seasonLabel, QI.seasonTypeFilter seasonTypeLabel]
    _ -> Left ("Could not ground find time window '" <> kind window <> "' against ontology-backed find filters.")

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

bestPublicDimensionMatch :: Text -> Object -> Maybe Text
bestPublicDimensionMatch rawDimension objectValue =
  case sortOn publicDimensionRank matchingDimensions of
    attributeValue : _ -> Just (attributeName attributeValue)
    [] -> Nothing
  where
    rawKey = normalizedKey rawDimension
    objectPrefix = normalizedKey (objectName objectValue)
    matchingDimensions =
      [ attributeValue
      | attributeValue <- objectAttributes objectValue
      , attributeKind attributeValue == Dimension
      , attributeVisibility attributeValue == Public
      , publicDimensionScore rawKey objectPrefix (attributeName attributeValue) > 0
      ]
    publicDimensionRank attributeValue =
      ( Down (publicDimensionScore rawKey objectPrefix (attributeName attributeValue))
      , attributeName attributeValue
      )

publicDimensionScore :: Text -> Text -> Text -> Int
publicDimensionScore rawKey objectPrefix attributeNameValue
  | rawKey == attributeKey = 100
  | rawKey == T.replace objectPrefix "" attributeKey = 95
  | rawKey == T.replace "primary" "" attributeKey = 90
  | rawKey `T.isSuffixOf` attributeKey = 80
  | otherwise = 0
  where
    attributeKey = normalizedKey attributeNameValue

trendDimensionMatchesSubject :: Object -> Text -> Bool
trendDimensionMatchesSubject subjectObject rawDimension =
  let rawKey = normalizedKey rawDimension
      subjectKey = subjectMatchKey (objectName subjectObject)
   in subjectMatchKey rawDimension == subjectKey
        || (subjectKey `T.isInfixOf` rawKey && "name" `T.isInfixOf` rawKey)

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

requireComparisonFilters :: DraftTimeWindow -> Either Text [QI.Filter]
requireComparisonFilters window =
  -- Comparison uses a recent-games shape.
  -- The window can be any positive last-N value the user asked for.
  case (normalizedKey (kind window), value window) of
    ("lastngames", Just (QI.FilterInt gamesValue))
      | gamesValue > 0 -> Right [QI.lastNGamesFilter gamesValue]
    _ -> Left ("Could not ground comparison time window '" <> kind window <> "' against ontology-backed comparison filters.")

requireResolvedComparisonEntities :: SemanticDraft -> Either Text [QI.EntityRef]
requireResolvedComparisonEntities draft =
  -- Python resolves raw names against DuckDB before Haskell planning.
  -- Haskell only checks that the resolved entities are distinct and usable.
  let entityValues = resolvedEntities draft
      entityIds = map QI.entityId entityValues
   in if length entityValues >= 2 && length (nub entityIds) == length entityValues
        then Right entityValues
        else Left "Comparison drafts require at least two distinct data-resolved entities."

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

resolveFindGrounding :: Ontology -> SemanticDraft -> Object -> [QI.Filter] -> Maybe Int -> Either Text GroundedFind
resolveFindGrounding ontology draft targetObject findTimeFilters limitValue =
  case rankedCandidates of
    candidate : _ -> Right candidate
    [] ->
      Left
        ( "Could not ground find draft with subject '"
            <> subject draft
            <> "' and the requested filters against ontology objects, attributes, and links."
        )
  where
    rankedCandidates =
      sortOn findCandidateRank $
        mapMaybe (groundFindFactCandidate ontology draft targetObject findTimeFilters limitValue) (objects ontology)

findCandidateRank :: GroundedFind -> (Down Int, Text)
findCandidateRank candidate =
  (Down (findMatchScore candidate), objectName (findFactObject candidate))

groundFindFactCandidate :: Ontology -> SemanticDraft -> Object -> [QI.Filter] -> Maybe Int -> Object -> Maybe GroundedFind
groundFindFactCandidate ontology draft targetObject findTimeFilters limitValue factObjectValue = do
  _ <- findPath ontology 2 (objectName factObjectValue) (objectName targetObject)
  predicateValues <- mapM (resolveFindPredicateForFact ontology factObjectValue) (filters draft)
  displayDimensionValue <- identityDimension targetObject
  pure
    GroundedFind
      { findFactObject = factObjectValue
      , findTargetObject = targetObject
      , findDisplayDimensions = findDisplayDimensionsFor targetObject displayDimensionValue
      , findPredicateValues = predicateValues
      , findFilterValues = findTimeFilters
      , findLimitValue = limitValue
      , findAssumptions = assumptions draft
      , findMatchScore = findFactCandidateScore factObjectValue targetObject predicateValues
      }

findDisplayDimensionsFor :: Object -> Text -> [Text]
findDisplayDimensionsFor targetObject identityDimensionValue =
  case objectName targetObject of
    "Game" -> publicDimensionsNamed ["game_date", "season_year", "season_type"] targetObject
    _ ->
      nub $
        identityDimensionValue
          : publicDimensionsNamed
            ["game_date", "season_year", "season_type", "team_name", "team_abbreviation", "full_name"]
            targetObject

publicDimensionsNamed :: [Text] -> Object -> [Text]
publicDimensionsNamed dimensionNames objectValue =
  [ dimensionName
  | dimensionName <- dimensionNames
  , Just attributeValue <- [findAttribute objectValue dimensionName]
  , attributeKind attributeValue == Dimension
  , attributeVisibility attributeValue == Public
  ]

findFactCandidateScore :: Object -> Object -> [QI.FindPredicate] -> Int
findFactCandidateScore factObjectValue targetObject predicateValues =
  subjectFactAffinity targetObject factObjectValue
    + (10 * length [predicateValue | predicateValue <- predicateValues, QI.predicateTargetObject predicateValue == objectName factObjectValue])

resolveFindPredicateForFact :: Ontology -> Object -> DraftFilter -> Maybe QI.FindPredicate
resolveFindPredicateForFact ontology factObjectValue draftFilter = do
  rawField <- filterField draftFilter
  rawValue <- filterValue draftFilter
  opValue <- normalizeFindOp (filterOp draftFilter)
  (predicateObject, predicateAttribute) <- resolveFindPredicateAttribute ontology factObjectValue rawField
  pure
    QI.FindPredicate
      { QI.predicateTargetObject = objectName predicateObject
      , QI.predicateAttribute = attributeName predicateAttribute
      , QI.predicateOperator = opValue
      , QI.predicateFilterValue = rawValue
      }

normalizeFindOp :: Maybe Text -> Maybe QI.PredicateOp
normalizeFindOp maybeRawOp =
  case T.strip <$> maybeRawOp of
    Just "=" -> Just QI.OpEq
    Just ">" -> Just QI.OpGt
    Just ">=" -> Just QI.OpGte
    Just "<" -> Just QI.OpLt
    Just "<=" -> Just QI.OpLte
    _ -> normalizeFindWordOp maybeRawOp

normalizeFindWordOp :: Maybe Text -> Maybe QI.PredicateOp
normalizeFindWordOp maybeRawOp =
  case normalizedKey <$> maybeRawOp of
    Nothing -> Just QI.OpEq
    Just "" -> Just QI.OpEq
    Just "eq" -> Just QI.OpEq
    Just "equals" -> Just QI.OpEq
    Just "is" -> Just QI.OpEq
    Just "over" -> Just QI.OpGt
    Just "above" -> Just QI.OpGt
    Just "greaterthan" -> Just QI.OpGt
    Just "gt" -> Just QI.OpGt
    Just "morethan" -> Just QI.OpGt
    Just "atleast" -> Just QI.OpGte
    Just "gte" -> Just QI.OpGte
    Just "under" -> Just QI.OpLt
    Just "below" -> Just QI.OpLt
    Just "lessthan" -> Just QI.OpLt
    Just "lt" -> Just QI.OpLt
    Just "atmost" -> Just QI.OpLte
    Just "lte" -> Just QI.OpLte
    _ -> Nothing

resolveFindPredicateAttribute :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
resolveFindPredicateAttribute ontology factObjectValue rawField =
  case objectIdentityAttributeMatch ontology factObjectValue rawField of
    Just matchValue -> Just matchValue
    Nothing -> bestReachableAttributeMatch ontology factObjectValue rawField

objectIdentityAttributeMatch :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
objectIdentityAttributeMatch ontology factObjectValue rawField =
  case
    [ (objectValue, attributeValue)
    | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
    , subjectMatchKey rawField == subjectMatchKey (objectName objectValue)
    , Just identityName <- [identityDimension objectValue]
    , Just attributeValue <- [findAttribute objectValue identityName]
    ]
    of
    matchValue : _ -> Just matchValue
    [] -> Nothing

bestReachableAttributeMatch :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
bestReachableAttributeMatch ontology factObjectValue rawField =
  case sortOn findAttributeRank matches of
    matchValue : _ -> Just matchValue
    [] -> Nothing
  where
    matches =
      [ (objectValue, attributeValue)
      | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
      , attributeValue <- objectAttributes objectValue
      , attributeVisibility attributeValue == Public
      , findAttributeScore rawField attributeValue > 0
      ]
    findAttributeRank (objectValue, attributeValue) =
      ( Down (findAttributeScore rawField attributeValue)
      , if objectName objectValue == objectName factObjectValue then (0 :: Int) else 1
      , objectName objectValue
      , attributeName attributeValue
      )

findAttributeScore :: Text -> OT.Attribute -> Int
findAttributeScore rawField attributeValue
  | rawKey == attributeKey = 100
  | rawKey == T.replace "total" "" attributeKey = 90
  | rawKey == T.replace "team" "" attributeKey = 85
  | rawKey `T.isSuffixOf` attributeKey = 80
  | otherwise = 0
  where
    rawKey = normalizedMeasureKey rawField
    attributeKey = normalizedMeasureKey (attributeName attributeValue)

reachableObjects :: Ontology -> Object -> [Object]
reachableObjects ontology objectValue =
  [ candidateObject
  | candidateObject <- objects ontology
  , objectName candidateObject /= objectName objectValue
  , findPath ontology 2 (objectName objectValue) (objectName candidateObject) /= Nothing
  ]

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
  pure
    GroundedComparison
      { comparisonFactObject = factObjectValue
      , comparisonSubjectObject = subjectObject
      , comparisonMetricDef = metricValue
      , comparisonDisplayDimension = displayDimensionValue
      , comparisonFilterValues = filtersForComparison
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

requireRankingFilters :: DraftTimeWindow -> [DraftFilter] -> Either Text RankingFilterBundle
requireRankingFilters window draftFilters =
  -- Convert the draft's user-facing time window into the IR filters the planner knows.
  -- Recent rankings use last_n_games; season rankings use exact_season + season_type.
  case (normalizedKey (kind window), value window) of
    ("lastngames", Just (QI.FilterInt gamesValue))
      | gamesValue > 0 -> Right (RecentRanking gamesValue)
    ("season", Just (QI.FilterText seasonLabel)) -> do
      seasonTypeLabel <- requireSeasonType window draftFilters
      Right (SeasonRanking seasonLabel seasonTypeLabel)
    _ -> Left ("Could not ground ranking time window '" <> kind window <> "' against ontology-backed rank filters.")

rankingFilterValues :: RankingFilterBundle -> [QI.Filter]
rankingFilterValues rankingFilters =
  case rankingFilters of
    RecentRanking gamesValue -> [QI.lastNGamesFilter gamesValue]
    SeasonRanking seasonLabel seasonTypeLabel ->
      [QI.exactSeasonFilter seasonLabel, QI.seasonTypeFilter seasonTypeLabel]

requireSeasonType :: DraftTimeWindow -> [DraftFilter] -> Either Text Text
requireSeasonType window draftFilters =
  case seasonTypeFromFilters draftFilters <|> seasonTypeFromWindow window of
    Just seasonTypeLabel -> Right seasonTypeLabel
    Nothing ->
      Left "Season ranking requires an explicit season type such as regular season or playoffs."

seasonTypeFromFilters :: [DraftFilter] -> Maybe Text
seasonTypeFromFilters draftFilters =
  case mapMaybe seasonTypeFromFilter draftFilters of
    seasonTypeValue : _ -> Just seasonTypeValue
    [] -> Nothing

seasonTypeFromFilter :: DraftFilter -> Maybe Text
seasonTypeFromFilter draftFilter = do
  valueText <- draftFilterTextValue draftFilter
  let fieldKey = maybe "" normalizedKey (filterField draftFilter)
      valueSeasonType = normalizeSeasonType valueText
  if "seasontype" `T.isInfixOf` fieldKey || valueSeasonType /= Nothing
    then valueSeasonType
    else Nothing

seasonTypeFromWindow :: DraftTimeWindow -> Maybe Text
seasonTypeFromWindow window =
  case value window of
    Just (QI.FilterText textValue) -> normalizeSeasonType textValue
    _ -> normalizeSeasonType (kind window)

normalizeSeasonType :: Text -> Maybe Text
normalizeSeasonType rawValue =
  case normalizedKey rawValue of
    keyValue
      | "regularseason" `T.isInfixOf` keyValue -> Just "regular_season"
      | "regular" == keyValue -> Just "regular_season"
      | "playoffs" `T.isInfixOf` keyValue -> Just "playoffs"
      | "playoff" `T.isInfixOf` keyValue -> Just "playoffs"
      | "postseason" `T.isInfixOf` keyValue -> Just "playoffs"
      | "regularseason" == keyValue -> Just "regular_season"
      | "regular_season" == rawValue -> Just "regular_season"
      | otherwise -> Nothing

draftFilterTextValue :: DraftFilter -> Maybe Text
draftFilterTextValue draftFilter =
  case filterValue draftFilter of
    Just (QI.FilterText textValue) -> Just textValue
    Just (QI.FilterInt intValue) -> Just (T.pack (show intValue))
    Nothing -> Nothing

requireOptionalPositiveLimit :: Maybe Int -> Either Text (Maybe Int)
requireOptionalPositiveLimit maybeLimit =
  -- "Top N" is optional, but if present it must be positive.
  case maybeLimit of
    Nothing -> Right Nothing
    Just currentLimit
      | currentLimit > 0 -> Right (Just currentLimit)
      | otherwise -> Left "Ranking query limit must be positive when provided."

requireRankingSort :: Maybe Text -> Either Text (QI.MetricName -> QI.Order)
requireRankingSort maybeSort =
  -- Let rank questions express both "top/highest" and "bottom/lowest".
  case fmap normalizedKey maybeSort of
    Nothing -> Right QI.Desc
    Just "desc" -> Right QI.Desc
    Just "descending" -> Right QI.Desc
    Just "top" -> Right QI.Desc
    Just "highest" -> Right QI.Desc
    Just "most" -> Right QI.Desc
    Just "asc" -> Right QI.Asc
    Just "ascending" -> Right QI.Asc
    Just "bottom" -> Right QI.Asc
    Just "lowest" -> Right QI.Asc
    Just "least" -> Right QI.Asc
    _ -> Left "Could not ground ranking sort direction against the requested metric."

resolveSubjectObject :: Ontology -> Text -> Either Text Object
resolveSubjectObject ontology rawSubject =
  -- Map user-facing subject text to an ontology object.
  -- Example: "players" -> Player, "teams" -> Team.
  case matchingObjects of
    [objectValue] -> Right objectValue
    [] -> Left ("No ontology object matched draft subject '" <> rawSubject <> "'.")
    matches ->
      Left
        ( "Draft subject '"
            <> rawSubject
            <> "' is ambiguous across ontology objects: "
            <> T.intercalate ", " (map objectName matches)
            <> "."
        )
  where
    subjectKey = subjectMatchKey rawSubject
    matchingObjects =
      [ objectValue
      | objectValue <- objects ontology
      , subjectMatchKey (objectName objectValue) == subjectKey
      ]

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
  pure
    GroundedRanking
      { factObject = factObjectValue
      , subjectObject = subjectObject
      , metricDef = metricValue
      , displayDimension = dimensionValue
      , filterValues = rankingFilterValues rankingFilters
      , limitValue = maybeLimit
      , assumptionValues = assumptions draft
      , matchScore = metricMatchScore rawMeasure metricValue
      , subjectAffinityScore = subjectFactAffinity subjectObject factObjectValue
      }

requireRankingFactSurface :: RankingFilterBundle -> Object -> Maybe ()
requireRankingFactSurface rankingFilters factObjectValue =
  case rankingFilters of
    RecentRanking _ -> do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    SeasonRanking _ _ -> do
      _ <- findAttribute factObjectValue "season_year"
      _ <- findAttribute factObjectValue "season_type"
      case findAttribute factObjectValue "game_date" of
        Nothing -> Just ()
        Just _ -> Nothing

subjectFactAffinity :: Object -> Object -> Int
subjectFactAffinity subjectObject factObjectValue =
  -- Prefer fact objects whose name contains the subject name, like PlayerGame for Player.
  if normalizedKey (objectName subjectObject) `T.isInfixOf` normalizedKey (objectName factObjectValue)
    then 100
    else 0

trendFactAffinity :: Text -> Object -> Object -> Int
trendFactAffinity trendGrain subjectObject factObjectValue =
  subjectFactAffinity subjectObject factObjectValue + grainSurfaceScore
  where
    grainSurfaceScore =
      case (trendGrain, findAttribute factObjectValue "game_date") of
        ("season", Nothing) -> 50
        ("season", Just _) -> 0
        (_, Just _) -> 50
        _ -> 0

bestMetricMatch :: Text -> Object -> Maybe OT.MetricDef
bestMetricMatch rawMeasure objectValue =
  -- Choose the highest-scoring executable ontology metric for the user's measure phrase.
  case rankedExecutableMatches of
    metricValue : _ -> Just metricValue
    [] -> Nothing
  where
    rankedExecutableMatches =
      sortOn
        (\metricValue -> Down (metricMatchScore rawMeasure metricValue))
        [ metricValue
        | metricValue <- objectMetrics objectValue
        , metricExecutable metricValue
        , metricMatchScore rawMeasure metricValue > 0
        ]

metricMatchScore :: Text -> OT.MetricDef -> Int
metricMatchScore rawMeasure metricValue =
  -- Score how well a user-facing measure phrase maps to one ontology metric.
  maximum (0 : [score | (aliasKey, score) <- metricAliases metricValue, aliasKey == measureKey])
  where
    measureKey = normalizedMeasureKey rawMeasure

metricAliases :: OT.MetricDef -> [(Text, Int)]
metricAliases metricValue =
  -- Generate lexical aliases for a metric from its name, aggregation, and source attributes.
  -- Example: total_points can match "points", "pts", "scoring", or "total points".
  baseAliases <> aggregationAliases <> sourceAliases
  where
    metricKey = normalizedMeasureKey (metricName metricValue)
    sourceKeys = map normalizedMeasureKey (metricSourceAttributes metricValue)
    aggregationKey = normalizedKey (metricAggregation metricValue)
    baseAliases =
      (metricKey, 100)
        : [ (T.replace "total" "" metricKey, 75)
          | "total" `T.isInfixOf` metricKey
          , T.replace "total" "" metricKey /= ""
          ]
    sourceAliases =
      [ (sourceKey, 80)
      | sourceKey <- sourceKeys
      , aggregationKey `elem` ["sum", "identity"]
      ]
    aggregationAliases =
      concatMap (aliasesForAggregation aggregationKey metricKey) sourceKeys

aliasesForAggregation :: Text -> Text -> Text -> [(Text, Int)]
aliasesForAggregation aggregationKey metricKey sourceKey
  -- Add measure aliases based on aggregation style, like avg points -> average_points.
  | aggregationKey == "avg" =
      [ ("average" <> sourceKey, 95)
      , ("avg" <> sourceKey, 95)
      , (sourceKey <> "pergame", 90)
      , ("pergame" <> sourceKey, 85)
      ]
        <> pointsAverageAliases
  | aggregationKey == "sum" =
      [ ("total" <> sourceKey, 95)
      ]
        <> pointsTotalAliases
  | "pergame" `T.isSuffixOf` metricKey =
      [ ("average" <> sourceKey, 95)
      , ("avg" <> sourceKey, 95)
      , (sourceKey <> "pergame", 95)
      ]
        <> pointsAverageAliases
  | otherwise = []
  where
    pointsAverageAliases =
      if sourceKey `elem` ["points", "score"] || "points" `T.isInfixOf` metricKey
        then [("ppg", 95), ("averagepoints", 95), ("avgpoints", 95), ("averagescoring", 90)]
        else []
    pointsTotalAliases =
      if sourceKey `elem` ["points", "score"] || "points" `T.isInfixOf` metricKey
        then [("points", 85), ("pts", 85), ("scoring", 80)]
        else []

identityDimension :: Object -> Maybe Text
identityDimension objectValue =
  -- Pick the best public dimension to display for the subject row.
  -- Example: Player prefers full_name; Team prefers team_name.
  case sortOn identityRank publicDimensions of
    attributeValue : _ -> Just (attributeName attributeValue)
    [] -> Nothing
  where
    publicDimensions =
      [ attributeValue
      | attributeValue <- objectAttributes objectValue
      , attributeKind attributeValue == Dimension
      , attributeVisibility attributeValue == Public
      ]
    objectPrefix = normalizedKey (objectName objectValue)
    identityRank attributeValue =
      let attributeKey = normalizedKey (attributeName attributeValue)
       in if attributeKey == "fullname"
            then (0 :: Int, attributeKey)
            else
              if attributeKey == objectPrefix <> "name"
                then (1, attributeKey)
                else
                  if "name" `T.isSuffixOf` attributeKey
                    then (2, attributeKey)
                    else (3, attributeKey)

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
            , QI.linkedFilters = []
            , QI.orders = [orderBuilder (metricName (metricDef grounded))]
            , QI.limit = limitValue grounded
            , QI.assumptions = assumptionValues grounded
            }
      , QI.entityFilters = []
      , QI.comparison = Nothing
      }

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

findQuery :: GroundedFind -> QI.Query
findQuery grounded =
    QI.FindQuery
    QI.FindQuerySpec
      { QI.findCoreFactObject = objectName (findFactObject grounded)
      , QI.findTargetObject = objectName (findTargetObject grounded)
      , QI.findDisplayDimensions = findDisplayDimensions grounded
      , QI.findPredicates = findPredicateValues grounded
      , QI.findFilters = findFilterValues grounded
      , QI.findLimit = findLimitValue grounded
      , QI.findAssumptions = findAssumptions grounded
      }

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
            , QI.linkedFilters = []
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

singularKey :: Text -> Text
singularKey rawValue =
  -- Basic singularization for matching "players" to Player.
  let keyValue = normalizedKey rawValue
   in case T.stripSuffix "s" keyValue of
        Just singularValue -> singularValue
        Nothing -> keyValue

subjectMatchKey :: Text -> Text
subjectMatchKey rawValue =
  -- Remove harmless domain words before matching subjects to ontology objects.
  -- Example: "NBA players" grounds to Player.
  singularKey
    ( T.replace "league" ""
        ( T.replace "basketball" ""
            (T.replace "nba" "" (normalizedKey rawValue))
        )
    )

normalizedMeasureKey :: Text -> Text
normalizedMeasureKey rawValue =
  -- Normalize common measure aliases before metric matching.
  case normalizedKey rawValue of
    "pts" -> "points"
    "point" -> "points"
    "scoring" -> "points"
    "avgpoints" -> "averagepoints"
    "averagescoring" -> "averagepoints"
    "ppg" -> "ppg"
    keyValue -> keyValue

normalizedKey :: Text -> Text
normalizedKey =
  -- Lowercase and remove punctuation/spaces for simple lexical matching.
  T.filter isAlphaNum . T.toLower . T.strip

objectName :: Object -> Text
objectName OT.Object {OT.name = currentName} = currentName

objectAttributes :: Object -> [OT.Attribute]
objectAttributes OT.Object {OT.attributes = currentAttributes} = currentAttributes

objectMetrics :: Object -> [OT.MetricDef]
objectMetrics OT.Object {OT.metrics = currentMetrics} = currentMetrics

attributeName :: OT.Attribute -> Text
attributeName OT.Attribute {OT.name = currentName} = currentName

attributeKind :: OT.Attribute -> AttributeKind
attributeKind OT.Attribute {OT.kind = currentKind} = currentKind

attributeVisibility :: OT.Attribute -> AttributeVisibility
attributeVisibility OT.Attribute {OT.visibility = currentVisibility} = currentVisibility

metricName :: OT.MetricDef -> Text
metricName OT.MetricDef {OT.name = currentName} = currentName

metricAggregation :: OT.MetricDef -> Text
metricAggregation OT.MetricDef {OT.aggregation = currentAggregation} = currentAggregation

metricSourceAttributes :: OT.MetricDef -> [Text]
metricSourceAttributes OT.MetricDef {OT.source_attributes = currentSourceAttributes} = currentSourceAttributes

metricExecutable :: OT.MetricDef -> Bool
metricExecutable OT.MetricDef {OT.executable = currentExecutable} = currentExecutable
