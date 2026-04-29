{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Filters
  ( classifyOrdinaryMetricFilterFamily
  , hasSeasonFilters
  , isExactSeasonBundle
  , isGameDateWindowBundle
  , isRecentWindowBundle
  , isSeasonSurfaceBundle
  , isPastYearFilter
  , seasonFilterPair
  , validateMetricFilters
  , validateOrdinaryMetricFilterSurface
  , validateSeasonFilters
  ) where

import Control.Applicative ((<|>))
import Data.Text (Text)
import GroundedPlanning.Validation.Common.Ontology (requireFactAttribute)
import GroundedPlanning.Validation.Common.Types
import OntologyLayer.Types (Object)
import QueryModel.IR

validateMetricFilters :: [Filter] -> Either Text ()
validateMetricFilters filterValues =
  case classifyOrdinaryMetricFilterFamily filterValues of
    Right _ -> pure ()
    Left errorMessage -> Left errorMessage

validateOrdinaryMetricFilterSurface :: Object -> [Filter] -> Either Text ()
validateOrdinaryMetricFilterSurface factObject filterValues = do
  filterFamily <- classifyOrdinaryMetricFilterFamily filterValues
  case filterFamily of
    GameDateMetricWindow ->
      requireFactAttribute factObject "game_date" "Date-scoped metric queries require a fact surface that exposes game_date."
    SeasonMetricWindow -> pure ()
  if hasSeasonFilters filterValues
    then do
      requireFactAttribute factObject "season_year" "Season-scoped metric queries require a fact surface that exposes season_year."
      requireFactAttribute factObject "season_type" "Season-scoped metric queries require a fact surface that exposes season_type."
    else pure ()

classifyOrdinaryMetricFilterFamily :: [Filter] -> Either Text OrdinaryMetricFilterFamily
classifyOrdinaryMetricFilterFamily filterValues =
  if isSeasonSurfaceBundle filterValues
    then Right SeasonMetricWindow
    else
      if isGameDateWindowBundle filterValues
        then Right GameDateMetricWindow
        else Left "Metric queries require ontology-backed time filters such as last_n_games, last_n_days, past_year, date_from/date_to, all available data, or exact season plus season type."

isSeasonSurfaceBundle :: [Filter] -> Bool
isSeasonSurfaceBundle = isExactSeasonBundle

isRecentWindowBundle :: [Filter] -> Bool
isRecentWindowBundle filterValues =
  case spanLastNGamesFilters filterValues of
    ([lastNGamesFilterValue], remainingFilters)
      | Just gamesValue <- filterIntValue lastNGamesFilterValue
      , gamesValue > 0 ->
          null remainingFilters || isExactSeasonBundle remainingFilters
    _ -> False

isGameDateWindowBundle :: [Filter] -> Bool
isGameDateWindowBundle filterValues =
  validateGameDateWindowBundle filterValues == Right ()

validateGameDateWindowBundle :: [Filter] -> Either Text ()
validateGameDateWindowBundle filterValues = do
  if exactSeasonWithoutSeasonType
    then Left "Exact-season filters require a matching season_type filter."
    else pure ()
  if all supportedGameDateFilter filterValues
    then pure ()
    else Left "Unsupported metric time filter kind."
  validateAtMostOne "last_n_games"
  validateAtMostOne "last_n_days"
  validateAtMostOne "past_year"
  validateAtMostOne "date_from"
  validateAtMostOne "date_to"
  validatePrimaryWindowChoice
  mapM_ validateGameDateFilterValue filterValues
  where
    filterKinds = map filterKindText filterValues
    exactSeasonWithoutSeasonType =
      "exact_season" `elem` filterKinds && not ("season_type" `elem` filterKinds)
    supportedGameDateFilter filterValue =
      filterKindText filterValue `elem` ["last_n_games", "last_n_days", "past_year", "date_from", "date_to", "exact_season", "season_type"]
    validateAtMostOne kindValue =
      if length (filter (== kindValue) filterKinds) <= 1
        then pure ()
        else Left ("Duplicate " <> kindValue <> " filters are not supported.")
    primaryWindowKinds =
      [ kindValue
      | kindValue <- filterKinds
      , kindValue `elem` ["last_n_games", "last_n_days", "past_year"]
      ]
    validatePrimaryWindowChoice =
      if length primaryWindowKinds <= 1
        then pure ()
        else Left "Metric queries support one primary relative time window at a time."
    validateGameDateFilterValue filterValue =
      case filterKindText filterValue of
        "last_n_games" ->
          case filterIntValue filterValue of
            Just gamesValue | gamesValue > 0 -> pure ()
            _ -> Left "last_n_games filters require a positive integer value."
        "last_n_days" ->
          case filterIntValue filterValue of
            Just daysValue | daysValue > 0 -> pure ()
            _ -> Left "last_n_days filters require a positive integer value."
        "past_year" ->
          if filterValueRef filterValue == Nothing
            then pure ()
            else Left "past_year filters must not provide a value."
        "date_from" ->
          case filterTextValue filterValue of
            Just startDate | startDate /= "" -> pure ()
            _ -> Left "date_from filters require a non-empty date value."
        "date_to" ->
          case filterTextValue filterValue of
            Just endDate | endDate /= "" -> pure ()
            _ -> Left "date_to filters require a non-empty date value."
        "exact_season" ->
          case filterTextValue filterValue of
            Just seasonLabel | seasonLabel /= "" -> pure ()
            _ -> Left "exact_season filters require a non-empty season label."
        "season_type" ->
          case filterTextValue filterValue of
            Just seasonTypeLabel | seasonTypeLabel /= "" -> pure ()
            _ -> Left "season_type filters require a non-empty season type."
        _ -> Left "Unsupported metric time filter kind."

isExactSeasonBundle :: [Filter] -> Bool
isExactSeasonBundle filterValues =
  case seasonFilterPair filterValues of
    Just _ -> length filterValues == 2 && all isSeasonFilter filterValues
    Nothing -> False
  where
    isSeasonFilter filterValue =
      let kindValue = filterKindText filterValue
       in kindValue == "exact_season" || kindValue == "season_type"

hasSeasonFilters :: [Filter] -> Bool
hasSeasonFilters filterValues =
  any isSeasonFilter filterValues
  where
    isSeasonFilter filterValue =
      let kindValue = filterKindText filterValue
       in kindValue == "exact_season" || kindValue == "season_type"

validateSeasonFilters :: [Filter] -> Either Text ()
validateSeasonFilters filterValues =
  case seasonFilterPair filterValues of
    Just _ -> pure ()
    Nothing -> Left "Season queries require both an exact season label and an explicit season type."

seasonFilterPair :: [Filter] -> Maybe (Text, Text)
seasonFilterPair filterValues = do
  seasonLabel <- foldr pickExactSeasonValue Nothing filterValues
  seasonTypeLabel <- foldr pickSeasonTypeValue Nothing filterValues
  pure (seasonLabel, seasonTypeLabel)
  where
    pickExactSeasonValue filterValue currentValue =
      if filterKindText filterValue == "exact_season"
        then filterTextValue filterValue <|> currentValue
        else currentValue
    pickSeasonTypeValue filterValue currentValue =
      if filterKindText filterValue == "season_type"
        then filterTextValue filterValue <|> currentValue
        else currentValue

isPastYearFilter :: Filter -> Bool
isPastYearFilter filterValue =
  filterKindText filterValue == "past_year" && filterValueRef filterValue == Nothing

spanLastNGamesFilters :: [Filter] -> ([Filter], [Filter])
spanLastNGamesFilters filterValues =
  (filter isLastNGamesFilter filterValues, filter (not . isLastNGamesFilter) filterValues)

isLastNGamesFilter :: Filter -> Bool
isLastNGamesFilter filterValue =
  filterKindText filterValue == "last_n_games"
