{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Filters
  ( classifyOrdinaryMetricFilterFamily
  , hasSeasonFilters
  , isExactSeasonBundle
  , isPastYearFilter
  , seasonFilterPair
  , validateMetricFilters
  , validateSeasonFilters
  ) where

import Control.Applicative ((<|>))
import Data.Text (Text)
import GroundedPlanning.Validation.Common.Types
import QueryModel.IR

validateMetricFilters :: [Filter] -> Either Text ()
validateMetricFilters filterValues =
  case filterValues of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue
      , gamesValue > 0 -> pure ()
    _ -> Left "Query requires a positive LastNGames filter."

classifyOrdinaryMetricFilterFamily :: [Filter] -> Either Text OrdinaryMetricFilterFamily
classifyOrdinaryMetricFilterFamily filterValues =
  case filterValues of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue
      , gamesValue > 0 -> Right RecentMetricWindow
    _ ->
      if isExactSeasonBundle filterValues
        then Right SeasonMetricWindow
        else Left "Metric queries require either a positive LastNGames filter or an exact season plus season type filter bundle."

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
