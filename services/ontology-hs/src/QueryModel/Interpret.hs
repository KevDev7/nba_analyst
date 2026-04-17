-- Purpose:
-- Interpret the natural-language question into extracted semantic pieces.
--
-- Uses:
-- - the user question as raw text
--
-- Produces:
-- - a parsed-question structure for the current supported query families
--
-- Next:
-- - Match.hs

{-# LANGUAGE OverloadedStrings #-}

module QueryModel.Interpret where

import Data.Char (isAlphaNum, toLower)
import Data.Text (Text)
import qualified Data.Text as T

data ParsedQuestion = ParsedQuestion
  { originalQuestion :: Text
  , normalizedQuestion :: Text
  , extractedLimit :: Maybe Int
  , extractedWindowGames :: Maybe Int
  , extractedTimeGrain :: Maybe TimeGrainPhrase
  , extractedPastYear :: Bool
  , metricPhrase :: Text
  , playerConceptPresent :: Bool
  , teamConceptPresent :: Bool
  , objectRowsRequested :: Bool
  , entityPhrases :: [Text]
  , comparisonRequested :: Bool
  }
  deriving (Show, Eq)

data TimeGrainPhrase
  = Monthly
  deriving (Show, Eq)

interpretQuestion :: Text -> Either Text ParsedQuestion
interpretQuestion question = do
  let normalized = normalize question
      tokens = T.words normalized
      limitValue = extractLimit normalized tokens
      comparisonRequestedValue = "compare" `elem` tokens
      extractedTimeGrainValue = extractTimeGrain normalized
      extractedPastYearValue = "past year" `T.isInfixOf` normalized || "last year" `T.isInfixOf` normalized
      objectRowsRequestedValue =
        "players and their" `T.isInfixOf` normalized
          || "players with their" `T.isInfixOf` normalized
      entityPhrasesValue =
        filter (`elem` ["brunson", "haliburton", "jalen", "tyrese", "tatum", "jayson"]) tokens
      windowValue =
        if extractedPastYearValue
          then Right Nothing
          else Just <$> extractNumberAfter "last" tokens
  metricToken <- extractMetricPhrase normalized tokens
  parsedWindowValue <- windowValue
  pure
    ParsedQuestion
      { originalQuestion = question
      , normalizedQuestion = normalized
      , extractedLimit = limitValue
      , extractedWindowGames = parsedWindowValue
      , extractedTimeGrain = extractedTimeGrainValue
      , extractedPastYear = extractedPastYearValue
      , metricPhrase = metricToken
      , playerConceptPresent =
          any (`elem` ["player", "players", "scorer", "scorers"]) tokens
            || comparisonRequestedValue
            || "highest" `elem` tokens
      , teamConceptPresent = any (`elem` ["team", "teams"]) tokens
      , objectRowsRequested = objectRowsRequestedValue
      , entityPhrases = entityPhrasesValue
      , comparisonRequested = comparisonRequestedValue
      }

normalize :: Text -> Text
normalize =
  T.unwords . T.words . T.map normalizeChar . T.toLower
  where
    normalizeChar char
      | isAlphaNum char = toLower char
      | otherwise = ' '

extractNumberAfter :: Text -> [Text] -> Either Text Int
extractNumberAfter target tokens =
  case dropWhile (/= target) tokens of
    (_ : value : _) ->
      case reads (T.unpack value) of
        [(numberValue, "")] -> pure numberValue
        _ -> Left ("Could not parse number after '" <> target <> "'.")
    _ -> Left ("Could not find '" <> target <> "' in the question.")

extractTimeGrain :: Text -> Maybe TimeGrainPhrase
extractTimeGrain normalized
  | "monthly" `T.isInfixOf` normalized = Just Monthly
  | "by month" `T.isInfixOf` normalized = Just Monthly
  | otherwise = Nothing

extractOptionalNumberAfter :: Text -> [Text] -> Maybe Int
extractOptionalNumberAfter target tokens =
  case dropWhile (/= target) tokens of
    (_ : value : _) ->
      case reads (T.unpack value) of
        [(numberValue, "")] -> Just numberValue
        _ -> Nothing
    _ -> Nothing

extractLimit :: Text -> [Text] -> Maybe Int
extractLimit normalized tokens =
  case extractOptionalNumberAfter "top" tokens of
    Just value -> Just value
    Nothing
      | "highest" `T.isInfixOf` normalized -> Just 1
      | otherwise -> Nothing

extractMetricPhrase :: Text -> [Text] -> Either Text Text
extractMetricPhrase normalized tokens
  | "average points" `T.isInfixOf` normalized = Right "average points"
  | "avg points" `T.isInfixOf` normalized = Right "avg points"
  | "average scoring" `T.isInfixOf` normalized = Right "average scoring"
  | "scoring average" `T.isInfixOf` normalized = Right "scoring average"
  | "total points" `T.isInfixOf` normalized = Right "total points"
  | otherwise =
      case filter (`elem` ["points", "pts", "scoring", "scorer", "scorers"]) tokens of
        metricToken : _ -> Right metricToken
        [] -> Left "The current slices only support points-based questions."
