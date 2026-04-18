-- Purpose:
-- Capture loose semantic intent from a natural-language user question before it
-- is grounded to concrete ontology concepts.
--
-- Uses:
-- - raw user language
-- - optional NLP / model-assisted extraction
--
-- Produces:
-- - a best-effort semantic intent that is not yet committed to exact ontology
--   objects, metrics, dimensions, or paths
--
-- Next:
-- - QueryModel/Ground.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.Intent where

import Data.Char (isAlphaNum)
import Data.Text (Text)
import qualified Data.Text as T
import GHC.Generics (Generic)

data OrderingDirection
  = IntentAscending
  | IntentDescending
  deriving (Show, Eq, Generic)

data OrderingHint = OrderingHint
  { direction :: OrderingDirection
  , target :: Maybe Text
  }
  deriving (Show, Eq, Generic)

data ComparisonHint = ComparisonHint
  { targetObjectHint :: Maybe Text
  , entityMentions :: [Text]
  }
  deriving (Show, Eq, Generic)

data QueryIntent = QueryIntent
  { rawQuestion :: Text
  , objectMentions :: [Text]
  , metricMentions :: [Text]
  , dimensionMentions :: [Text]
  , filterMentions :: [Text]
  , timeMentions :: [Text]
  , recentGamesHint :: Maybe Int
  , orderingHint :: Maybe OrderingHint
  , limitHint :: Maybe Int
  , comparisonHint :: Maybe ComparisonHint
  }
  deriving (Show, Eq, Generic)

emptyIntent :: Text -> QueryIntent
emptyIntent questionText =
  QueryIntent
    { rawQuestion = questionText
    , objectMentions = []
    , metricMentions = []
    , dimensionMentions = []
    , filterMentions = []
    , timeMentions = []
    , recentGamesHint = Nothing
    , orderingHint = Nothing
    , limitHint = Nothing
    , comparisonHint = Nothing
    }

extractRecentPlayerRankingIntent :: Text -> Maybe QueryIntent
extractRecentPlayerRankingIntent questionText
  | not (isRankingQuestion questionTerms) = Nothing
  | not (mentionsRecentGames questionTerms) = Nothing
  | not (mentionsPlayerConcept questionTerms) = Nothing
  | not (mentionsPointsConcept questionTerms) = Nothing
  | otherwise =
      let recentGames = extractRecentGames questionTerms
          explicitLimit = extractTopLimit questionTerms
          inferredLimit =
            case explicitLimit of
              Just _ -> explicitLimit
              Nothing ->
                if any (`elem` questionTerms) ["most", "highest", "best"]
                  then Just 1
                  else Nothing
          objectHints =
            if any (`elem` questionTerms) ["player", "players"]
              then ["player"]
              else ["player", "scorer"]
          metricHints =
            if any (`elem` questionTerms) ["points", "pts"]
              then ["total_points"]
              else ["total_points", "scoring"]
       in recentGames >>= \gamesValue ->
            Just
              ( (emptyIntent questionText)
                  { objectMentions = objectHints
                  , metricMentions = metricHints
                  , filterMentions = ["last_n_games"]
                  , timeMentions = ["recent_games"]
                  , recentGamesHint = Just gamesValue
                  , orderingHint = Just (OrderingHint IntentDescending (Just "total_points"))
                  , limitHint = inferredLimit
                  }
              )
  where
    questionTerms = questionTokens questionText

mentionsPlayerConcept :: [Text] -> Bool
mentionsPlayerConcept tokens =
  any (`elem` tokens) ["player", "players", "scorer", "scorers"]

mentionsPointsConcept :: [Text] -> Bool
mentionsPointsConcept tokens =
  not (any (`elem` tokens) ["average", "avg"])
    && any (`elem` tokens) ["points", "pts", "scoring", "scorer", "scorers"]

isRankingQuestion :: [Text] -> Bool
isRankingQuestion tokens =
  isJustTextIntPair "top" tokens || any (`elem` tokens) ["most", "highest", "best"]

mentionsRecentGames :: [Text] -> Bool
mentionsRecentGames tokens =
  extractRecentGames tokens /= Nothing

extractTopLimit :: [Text] -> Maybe Int
extractTopLimit = extractKeywordIntPair "top"

extractRecentGames :: [Text] -> Maybe Int
extractRecentGames tokens =
  go tokens
  where
    go ("last" : numberToken : unitToken : remainingTokens)
      | unitToken `elem` ["game", "games"] =
          case readPositiveInt numberToken of
            Just intValue -> Just intValue
            Nothing -> go (numberToken : unitToken : remainingTokens)
    go (_ : remainingTokens) = go remainingTokens
    go [] = Nothing

extractKeywordIntPair :: Text -> [Text] -> Maybe Int
extractKeywordIntPair keyword tokens =
  go tokens
  where
    go (currentToken : nextToken : remainingTokens)
      | currentToken == keyword =
          case readPositiveInt nextToken of
            Just intValue -> Just intValue
            Nothing -> go (nextToken : remainingTokens)
    go (_ : remainingTokens) = go remainingTokens
    go [] = Nothing

isJustTextIntPair :: Text -> [Text] -> Bool
isJustTextIntPair keyword tokens =
  case extractKeywordIntPair keyword tokens of
    Just _ -> True
    Nothing -> False

readPositiveInt :: Text -> Maybe Int
readPositiveInt token =
  case reads (T.unpack token) of
    [(intValue, "")] | intValue > 0 -> Just intValue
    _ -> Nothing

questionTokens :: Text -> [Text]
questionTokens questionText =
  filter (not . T.null) $
    T.words $
      T.map normalizeChar (T.toLower questionText)
  where
    normalizeChar currentChar
      | isAlphaNum currentChar = currentChar
      | otherwise = ' '

tokens :: Text -> [Text]
tokens = questionTokens
