{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Filters
  ( classifyOrdinaryMetricFilterFamily
  , hasSeasonFilters
  , isExactSeasonBundle
  , isRecentWindowBundle
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
    Left _ -> Left "Query requires a positive LastNGames filter, optionally scoped by exact season plus season type."

validateOrdinaryMetricFilterSurface :: Object -> [Filter] -> Either Text ()
validateOrdinaryMetricFilterSurface factObject filterValues = do
  filterFamily <- classifyOrdinaryMetricFilterFamily filterValues
  case filterFamily of
    RecentMetricWindow ->
      requireFactAttribute factObject "game_date" "Recent metric queries require a fact surface that exposes game_date."
    SeasonMetricWindow -> pure ()
  if hasSeasonFilters filterValues
    then do
      requireFactAttribute factObject "season_year" "Season-scoped metric queries require a fact surface that exposes season_year."
      requireFactAttribute factObject "season_type" "Season-scoped metric queries require a fact surface that exposes season_type."
    else pure ()

classifyOrdinaryMetricFilterFamily :: [Filter] -> Either Text OrdinaryMetricFilterFamily
classifyOrdinaryMetricFilterFamily filterValues =
  if isRecentWindowBundle filterValues
    then Right RecentMetricWindow
    else
      if isExactSeasonBundle filterValues
        then Right SeasonMetricWindow
        else Left "Metric queries require either a positive LastNGames filter or an exact season plus season type filter bundle."

isRecentWindowBundle :: [Filter] -> Bool
isRecentWindowBundle filterValues =
  case spanLastNGamesFilters filterValues of
    ([lastNGamesFilterValue], remainingFilters)
      | Just gamesValue <- filterIntValue lastNGamesFilterValue
      , gamesValue > 0 ->
          null remainingFilters || isExactSeasonBundle remainingFilters
    _ -> False

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
