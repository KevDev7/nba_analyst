{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Normalize
  ( draftTask
  , normalizeFindOp
  , normalizeFindWordOp
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
import qualified QueryModel.IR as QI
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
    "week" -> Just "week"
    "weekly" -> Just "week"
    "calendarweek" -> Just "week"
    "month" -> Just "month"
    "monthly" -> Just "month"
    "calendarmonth" -> Just "month"
    "season" -> Just "season"
    "seasonal" -> Just "season"
    _ -> Nothing

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
