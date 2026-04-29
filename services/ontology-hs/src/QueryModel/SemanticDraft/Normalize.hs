{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Normalize
  ( draftTask
  , normalizeSeasonType
  , normalizeTrendGrain
  , normalizedKey
  , normalizedMeasureKey
  , singularKey
  , subjectMatchKey
  ) where

import Data.Char (isAlphaNum)
import Data.Text (Text)
import qualified Data.Text as T
import QueryModel.SemanticDraft.Types

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
    "object" -> DraftObject
    "objects" -> DraftObject
    "objectrows" -> DraftObject
    "entityrows" -> DraftObject
    _ -> DraftUnknown rawTask

normalizeTrendGrain :: Text -> Maybe Text
normalizeTrendGrain rawGrain =
  case normalizedKey rawGrain of
    "day" -> Just "day"
    "daily" -> Just "day"
    "date" -> Just "day"
    "game" -> Just "day"
    "gameday" -> Just "day"
    "week" -> Just "week"
    "weekly" -> Just "week"
    "calendarweek" -> Just "week"
    "gameweek" -> Just "week"
    "month" -> Just "month"
    "monthly" -> Just "month"
    "calendarmonth" -> Just "month"
    "gamemonth" -> Just "month"
    "season" -> Just "season"
    "seasonal" -> Just "season"
    _ -> Nothing

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
