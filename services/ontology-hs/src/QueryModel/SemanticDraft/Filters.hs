{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Filters
  ( draftFilterTextValue
  , findWindowFilters
  , rankingFilterValues
  , requireComparisonFilters
  , requireDraftMeasure
  , requireDraftMeasureForFamily
  , requireFindFilters
  , requireOptionalPositiveLimit
  , requireRankingFilters
  , requireRankingSort
  , requireResolvedComparisonEntities
  , requireSeasonType
  , requireTrendFilters
  , requireTrendGrain
  , seasonTypeFromFilter
  , seasonTypeFromFilters
  , seasonTypeFromWindow
  , trendSeasonTypeFilters
  , trendWindowFilters
  ) where

import Control.Applicative ((<|>))
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
