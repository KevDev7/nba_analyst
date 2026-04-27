{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Filters
  ( requireLastNGames
  , seasonFilterPair
  ) where

import Control.Applicative ((<|>))
import Data.Text (Text)
import QueryModel.IR

requireLastNGames :: [Filter] -> Either Text Int
requireLastNGames filterValues =
  case filterValues of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue -> Right gamesValue
    _ -> Left "Only a single LastNGames filter is supported."

seasonFilterPair :: [Filter] -> Maybe (Text, Text)
seasonFilterPair filterValues = do
  seasonLabelValue <- foldr pickExactSeasonValue Nothing filterValues
  seasonTypeValue <- foldr pickSeasonTypeValue Nothing filterValues
  pure (seasonLabelValue, seasonTypeValue)
  where
    pickExactSeasonValue filterValue currentValue =
      if filterKindText filterValue == "exact_season"
        then filterTextValue filterValue <|> currentValue
        else currentValue
    pickSeasonTypeValue filterValue currentValue =
      if filterKindText filterValue == "season_type"
        then filterTextValue filterValue <|> currentValue
        else currentValue
