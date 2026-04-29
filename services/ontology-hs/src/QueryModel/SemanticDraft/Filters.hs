{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Filters
  ( aggregateTimeScope
  , draftMeasurePhrases
  , draftFilterTextValue
  , draftFilterIsTimeScopeFilter
  , findTimeScope
  , findWindowFilters
  , comparisonTimeScope
  , objectTimeScope
  , rankingTimeScope
  , requireComparisonFilters
  , requireDraftMeasure
  , requireDraftMeasureForFamily
  , requireFindFilters
  , requireOptionalPositiveLimit
  , requireRankingSort
  , requireResolvedComparisonEntities
  , normalizeTrendGrain
  , requireSeasonType
  , requireTrendGrain
  , seasonTypeFromFilter
  , seasonTypeFromFilters
  , seasonTypeFromWindow
  , seasonYearFromFilter
  , seasonYearFromFilters
  , trendTimeScope
  , timeScopeFilters
  ) where

import Control.Applicative ((<|>))
import Data.Char (isDigit)
import Data.List (nub)
import Data.Maybe (mapMaybe)
import Data.Text (Text)
import qualified Data.Text as T
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Normalize
import QueryModel.SemanticDraft.Types

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

draftMeasurePhrases :: SemanticDraft -> [Text]
draftMeasurePhrases draft =
  dedupeMeasures $
    [ rawMeasure
    | Just rawMeasure <- [measure draft]
    , T.strip rawMeasure /= ""
    ]
      <> [ rawMeasure
         | rawMeasure <- measures draft
         , T.strip rawMeasure /= ""
         ]

dedupeMeasures :: [Text] -> [Text]
dedupeMeasures rawMeasures =
  case rawMeasures of
    [] -> []
    rawMeasure : remaining ->
      rawMeasure
        : dedupeMeasures
          [ candidate
          | candidate <- remaining
          , normalizedMeasureKey candidate /= normalizedMeasureKey rawMeasure
          ]

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

trendTimeScope :: Text -> DraftTimeWindow -> [DraftFilter] -> Either Text TimeScope
trendTimeScope trendGrain window draftFilters =
  -- Trend has two separate time concepts:
  -- grain = how to bucket the answer; time scope = which rows are included.
  case normalizedKey (kind window) of
    "lastndays" ->
      case value window of
        Just (QI.FilterInt daysValue) | daysValue > 0 -> Right (LastNDays daysValue)
        _ -> Left "Trend last_n_days time scopes require a positive integer value."
    "lastmonth" -> Right (LastNDays 30)
    "pastyear" -> Right PastYear
    "since" -> sinceDateScope window
    "sincedate" -> sinceDateScope window
    "fromdate" -> sinceDateScope window
    "afterdate" -> sinceDateScope window
    "until" -> untilDateScope window
    "untildate" -> untilDateScope window
    "todate" -> untilDateScope window
    "beforedate" -> untilDateScope window
    "between" -> betweenDateScope window
    "betweendates" -> betweenDateScope window
    "all" -> trendAllAvailableScope window draftFilters
    "allavailable" -> trendAllAvailableScope window draftFilters
    "none" -> trendAllAvailableScope window draftFilters
    "unspecified" -> trendAllAvailableScope window draftFilters
    "season" -> do
      seasonLabel <- requireSeasonYear window draftFilters
      seasonTypeLabel <- requireSeasonType window draftFilters
      Right (ExactSeason seasonLabel seasonTypeLabel)
    "lastngames" ->
      Left "Trend drafts do not support last_n_games time scopes yet because trend bucketing needs a calendar/date scope."
    grainKey
      | normalizeTrendGrain grainKey == Just trendGrain -> trendAllAvailableScope window draftFilters
    _ -> Left ("Could not ground trend time window '" <> kind window <> "' against ontology-backed trend filters.")

trendAllAvailableScope :: DraftTimeWindow -> [DraftFilter] -> Either Text TimeScope
trendAllAvailableScope window draftFilters =
  case seasonYearFromFilters draftFilters <|> seasonYearFromWindow window of
    Just seasonLabel -> do
      seasonTypeLabel <- requireSeasonType window draftFilters
      Right (ExactSeason seasonLabel seasonTypeLabel)
    Nothing ->
      case seasonTypeFromFilters draftFilters of
        Just seasonTypeLabel -> Right (SeasonTypeOnly seasonTypeLabel)
        Nothing -> Right AllAvailable

findWindowFilters :: DraftTimeWindow -> [DraftFilter] -> Either Text [QI.Filter]
findWindowFilters window draftFilters =
  -- Preserve find-query time intent as planner filters instead of silently
  -- dropping it. Validation/compilation later proves the fact surface can run it.
  timeScopeFilters <$> findTimeScope window draftFilters

findTimeScope :: DraftTimeWindow -> [DraftFilter] -> Either Text TimeScope
findTimeScope window draftFilters =
  -- Find queries may retrieve rows across all available data, over a date
  -- window, or inside an exact season. Keep that as time scope, not predicates.
  case (normalizedKey (kind window), value window) of
    ("all", _) -> Right AllAvailable
    ("allavailable", _) -> Right AllAvailable
    ("none", _) -> Right AllAvailable
    ("unspecified", _) -> Right AllAvailable
    ("lastngames", Just (QI.FilterInt gamesValue))
      | gamesValue > 0 -> do
          seasonFilters <- seasonConstraintFilters window draftFilters
          Right (RecentGames gamesValue seasonFilters)
    ("lastndays", Just (QI.FilterInt daysValue))
      | daysValue > 0 -> Right (LastNDays daysValue)
    ("lastmonth", _) -> Right (LastNDays 30)
    ("pastyear", _) -> Right PastYear
    ("since", _) -> sinceDateScope window
    ("sincedate", _) -> sinceDateScope window
    ("fromdate", _) -> sinceDateScope window
    ("afterdate", _) -> sinceDateScope window
    ("until", _) -> untilDateScope window
    ("untildate", _) -> untilDateScope window
    ("todate", _) -> untilDateScope window
    ("beforedate", _) -> untilDateScope window
    ("between", _) -> betweenDateScope window
    ("betweendates", _) -> betweenDateScope window
    ("daterange", _) -> betweenDateScope window
    ("season", _) -> do
      seasonLabel <- requireSeasonYear window draftFilters
      seasonTypeLabel <- requireSeasonType window draftFilters
      Right (ExactSeason seasonLabel seasonTypeLabel)
    _ -> Left ("Could not ground find time window '" <> kind window <> "' against ontology-backed find filters.")

requireComparisonFilters :: DraftTimeWindow -> [DraftFilter] -> Either Text [QI.Filter]
requireComparisonFilters window draftFilters =
  timeScopeFilters <$> comparisonTimeScope window draftFilters

comparisonTimeScope :: DraftTimeWindow -> [DraftFilter] -> Either Text TimeScope
comparisonTimeScope window draftFilters =
  -- A real TimeScope lets comparison choose the right ontology fact surface
  -- instead of assuming every comparison means "last N games".
  timeScopeForFamily "comparison" window draftFilters

rankingTimeScope :: DraftTimeWindow -> [DraftFilter] -> Either Text TimeScope
rankingTimeScope window draftFilters =
  -- Ranking uses the shared TimeScope shape now, but still lowers to the same
  -- canonical IR filters that downstream planning already understands.
  timeScopeForFamily "ranking" window draftFilters

objectTimeScope :: DraftTimeWindow -> [DraftFilter] -> Either Text TimeScope
objectTimeScope window draftFilters =
  -- Object rows use the same time-scope contract as rankings: recent windows
  -- use game facts; exact seasons use season facts.
  timeScopeForFamily "object" window draftFilters

aggregateTimeScope :: DraftTimeWindow -> [DraftFilter] -> Either Text TimeScope
aggregateTimeScope window draftFilters =
  -- Aggregates share the same time-scope contract, but keep their grouping and
  -- result-filter semantics separate from ranking.
  timeScopeForFamily "aggregate" window draftFilters

timeScopeForFamily :: Text -> DraftTimeWindow -> [DraftFilter] -> Either Text TimeScope
timeScopeForFamily familyName window draftFilters =
  case (normalizedKey (kind window), value window) of
    ("lastngames", Just (QI.FilterInt gamesValue))
      | gamesValue > 0 -> do
          seasonFilters <- seasonConstraintFilters window draftFilters
          Right (RecentGames gamesValue seasonFilters)
    ("lastndays", Just (QI.FilterInt daysValue))
      | daysValue > 0 -> Right (LastNDays daysValue)
    ("lastmonth", _) -> Right (LastNDays 30)
    ("pastyear", _) -> Right PastYear
    ("all", _) -> Right AllAvailable
    ("allavailable", _) -> Right AllAvailable
    ("none", _) -> Right AllAvailable
    ("unspecified", _) -> Right AllAvailable
    ("since", _) -> sinceDateScope window
    ("sincedate", _) -> sinceDateScope window
    ("fromdate", _) -> sinceDateScope window
    ("afterdate", _) -> sinceDateScope window
    ("until", _) -> untilDateScope window
    ("untildate", _) -> untilDateScope window
    ("todate", _) -> untilDateScope window
    ("beforedate", _) -> untilDateScope window
    ("between", _) -> betweenDateScope window
    ("betweendates", _) -> betweenDateScope window
    ("daterange", _) -> betweenDateScope window
    ("season", _) -> do
      seasonLabel <- requireSeasonYear window draftFilters
      seasonTypeLabel <- requireSeasonType window draftFilters
      Right (ExactSeason seasonLabel seasonTypeLabel)
    _ -> Left ("Could not ground " <> familyName <> " time window '" <> kind window <> "' against ontology-backed " <> familyName <> " filters.")

timeScopeFilters :: TimeScope -> [QI.Filter]
timeScopeFilters currentTimeScope =
  case currentTimeScope of
    RecentGames gamesValue seasonFilters -> QI.lastNGamesFilter gamesValue : seasonFilters
    LastNDays daysValue -> [QI.lastNDaysFilter daysValue]
    ExactSeason seasonLabel seasonTypeLabel -> [QI.exactSeasonFilter seasonLabel, QI.seasonTypeFilter seasonTypeLabel]
    SeasonTypeOnly seasonTypeLabel -> [QI.seasonTypeFilter seasonTypeLabel]
    PastYear -> [QI.pastYearFilter]
    DateRange maybeStartDate maybeEndDate -> maybe [] (\startDate -> [QI.dateFromFilter startDate]) maybeStartDate <> maybe [] (\endDate -> [QI.dateToFilter endDate]) maybeEndDate
    AllAvailable -> []

sinceDateScope :: DraftTimeWindow -> Either Text TimeScope
sinceDateScope window =
  case draftWindowTextValue window of
    Just startDate -> Right (DateRange (Just (lowerDateBound startDate)) Nothing)
    Nothing -> Left "Since-date time windows require a date value."

untilDateScope :: DraftTimeWindow -> Either Text TimeScope
untilDateScope window =
  case draftWindowTextValue window of
    Just endDate -> Right (DateRange Nothing (Just (upperDateBound endDate)))
    Nothing -> Left "Until-date time windows require a date value."

betweenDateScope :: DraftTimeWindow -> Either Text TimeScope
betweenDateScope window =
  case draftWindowTextValue window >>= parseDateRangeValue of
    Just (startDate, endDate) -> Right (DateRange (Just (lowerDateBound startDate)) (Just (upperDateBound endDate)))
    Nothing -> Left "Between-date time windows require a value like YYYY-MM-DD to YYYY-MM-DD."

draftWindowTextValue :: DraftTimeWindow -> Maybe Text
draftWindowTextValue window =
  case value window of
    Just (QI.FilterText textValue) | T.strip textValue /= "" -> Just (T.strip textValue)
    _ -> Nothing

parseDateRangeValue :: Text -> Maybe (Text, Text)
parseDateRangeValue rawValue =
  let normalizedValue = T.strip rawValue
      parseWith separator =
        case T.splitOn separator normalizedValue of
          [startDate, endDate]
            | T.strip startDate /= "" && T.strip endDate /= "" ->
                Just (T.strip startDate, T.strip endDate)
          _ -> Nothing
   in parseWith " to " <|> parseWith " through " <|> parseWith " and " <|> parseWith "|" <|> parseWith ","

lowerDateBound :: Text -> Text
lowerDateBound rawValue =
  if isFourDigitYear rawValue
    then T.strip rawValue <> "-01-01"
    else T.strip rawValue

upperDateBound :: Text -> Text
upperDateBound rawValue =
  if isFourDigitYear rawValue
    then T.strip rawValue <> "-12-31"
    else T.strip rawValue

isFourDigitYear :: Text -> Bool
isFourDigitYear rawValue =
  let strippedValue = T.strip rawValue
   in T.length strippedValue == 4 && T.all isDigit strippedValue

draftFilterIsTimeScopeFilter :: DraftFilter -> Bool
draftFilterIsTimeScopeFilter draftFilter =
  maybe False isTimeScopeField (filterField draftFilter)
    || maybe False isTimeScopeValue (draftFilterTextValue draftFilter)
  where
    isTimeScopeField rawField =
      let fieldKey = normalizedKey rawField
       in fieldKey `elem` ["season", "seasonyear", "seasons", "year", "seasontype"]
            || fieldKey `elem` ["date", "gamedate", "datefrom", "dateto", "since", "until", "through"]
            || "seasontype" `T.isInfixOf` fieldKey
    isTimeScopeValue rawValue =
      normalizeSeasonType rawValue /= Nothing

requireResolvedComparisonEntities :: SemanticDraft -> Either Text [QI.EntityRef]
requireResolvedComparisonEntities draft =
  -- Python resolves raw names against DuckDB before Haskell planning.
  -- Haskell only checks that the resolved entities are distinct and usable.
  let entityValues = resolvedEntities draft
      entityIds = map QI.entityId entityValues
   in if length entityValues >= 2 && length (nub entityIds) == length entityValues
        then Right entityValues
        else Left "Comparison drafts require at least two distinct data-resolved entities."

seasonConstraintFilters :: DraftTimeWindow -> [DraftFilter] -> Either Text [QI.Filter]
seasonConstraintFilters window draftFilters =
  case seasonYearFromFilters draftFilters <|> seasonYearFromWindow window of
    Just seasonLabel ->
      do
        seasonTypeLabel <- requireSeasonType window draftFilters
        Right [QI.exactSeasonFilter seasonLabel, QI.seasonTypeFilter seasonTypeLabel]
    Nothing -> Right []

requireSeasonType :: DraftTimeWindow -> [DraftFilter] -> Either Text Text
requireSeasonType window draftFilters =
  case seasonTypeFromFilters draftFilters <|> seasonTypeFromWindow window of
    Just seasonTypeLabel -> Right seasonTypeLabel
    Nothing ->
      Left "Season queries require an explicit season type such as regular season or playoffs."

requireSeasonYear :: DraftTimeWindow -> [DraftFilter] -> Either Text Text
requireSeasonYear window draftFilters =
  case seasonYearFromFilters draftFilters <|> seasonYearFromWindow window of
    Just seasonLabel -> Right seasonLabel
    Nothing -> Left "Season queries require an explicit season year such as 2025-26."

seasonTypeFromFilters :: [DraftFilter] -> Maybe Text
seasonTypeFromFilters draftFilters =
  case mapMaybe seasonTypeFromFilter draftFilters of
    seasonTypeValue : _ -> Just seasonTypeValue
    [] -> Nothing

seasonYearFromFilters :: [DraftFilter] -> Maybe Text
seasonYearFromFilters draftFilters =
  case mapMaybe seasonYearFromFilter draftFilters of
    seasonYearValue : _ -> Just seasonYearValue
    [] -> Nothing

seasonYearFromFilter :: DraftFilter -> Maybe Text
seasonYearFromFilter draftFilter = do
  valueText <- draftFilterTextValue draftFilter
  let fieldKey = maybe "" normalizedKey (filterField draftFilter)
  if fieldKey `elem` ["season", "seasonyear", "seasons", "year"]
    then normalizeSeasonYear valueText
    else Nothing

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

seasonYearFromWindow :: DraftTimeWindow -> Maybe Text
seasonYearFromWindow window =
  case value window of
    Just (QI.FilterText textValue) -> normalizeSeasonYear textValue
    _ -> normalizeSeasonYear (kind window)

normalizeSeasonYear :: Text -> Maybe Text
normalizeSeasonYear rawValue =
  let strippedValue = T.strip rawValue
      normalizedValue = T.filter (\character -> isDigit character || character == '-') strippedValue
      compactValue = T.filter isDigit strippedValue
   in if T.length normalizedValue == 7 && T.index normalizedValue 4 == '-'
        then Just normalizedValue
        else
          if T.length compactValue == 4
            then Just ("20" <> T.take 2 compactValue <> "-" <> T.drop 2 compactValue)
            else Nothing

draftFilterTextValue :: DraftFilter -> Maybe Text
draftFilterTextValue draftFilter =
  case filterValue draftFilter of
    Just (QI.FilterText textValue) -> Just textValue
    Just (QI.FilterInt intValue) -> Just (T.pack (show intValue))
    Just (QI.FilterDouble doubleValue) -> Just (T.pack (show doubleValue))
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
