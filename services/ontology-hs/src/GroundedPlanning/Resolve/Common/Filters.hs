{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Filters
  ( metricTimeFilterKind
  , requireLastNGames
  , seasonFilterPair
  ) where

import Control.Applicative ((<|>))
import Data.Text (Text)
import qualified Data.Text as T
import QueryModel.IR

metricTimeFilterKind :: [Filter] -> Text
metricTimeFilterKind filterValues =
  case filterValues of
    [] -> "all"
    _ ->
      let kinds = map filterKindText filterValues
       in if "last_n_games" `elem` kinds
            then "last_n_games"
            else
              if "last_n_days" `elem` kinds
                then "last_n_days"
                else
                  if "past_year" `elem` kinds
                    then "past_year"
                    else
                      if "date_from" `elem` kinds && "date_to" `elem` kinds
                        then "date_range"
                        else
                          if "date_from" `elem` kinds
                            then "since_date"
                            else
                              if "date_to" `elem` kinds
                                then "until_date"
                                else
                                  if "exact_season" `elem` kinds && "season_type" `elem` kinds
                                    then "exact_season+season_type"
                                    else T.intercalate "+" kinds

requireLastNGames :: [Filter] -> Either Text Int
requireLastNGames filterValues =
  case [gamesValue | filterValue <- filterValues, filterKindText filterValue == "last_n_games", Just gamesValue <- [filterIntValue filterValue], gamesValue > 0] of
    [gamesValue] -> Right gamesValue
    _ -> Left "Exactly one positive LastNGames filter is required."

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
