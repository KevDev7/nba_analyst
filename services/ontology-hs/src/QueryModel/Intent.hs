-- Purpose:
-- Capture loose semantic intent from a natural-language user question before it
-- is grounded to concrete ontology concepts.
--
-- Uses:
-- - raw user language
-- - lightweight semantic extraction heuristics
--
-- Produces:
-- - a best-effort semantic intent that is not yet committed to exact ontology
--   objects, metrics, dimensions, or fact surfaces
--
-- Next:
-- - QueryModel/Ground.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.Intent where

import Data.Char (isAlphaNum, isSpace)
import Data.List (nub)
import Data.Maybe (mapMaybe)
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

data IntentFilter
  = IntentLastNGames Int
  | IntentExactSeason Text
  | IntentSeasonType Text
  | IntentPastYear
  deriving (Show, Eq, Generic)

data LinkedFilterHint = LinkedFilterHint
  { targetObject :: Text
  , attribute :: Text
  , value :: Text
  }
  deriving (Show, Eq, Generic)

data QueryShapeHint
  = HintMetricQuery
  | HintObjectQuery
  | HintTrendQuery
  | HintComparisonQuery
  deriving (Show, Eq, Generic)

data QueryIntent = QueryIntent
  { rawQuestion :: Text
  , queryShapeHints :: [QueryShapeHint]
  , objectMentions :: [Text]
  , metricMentions :: [Text]
  , dimensionMentions :: [Text]
  , filters :: [IntentFilter]
  , linkedFilters :: [LinkedFilterHint]
  , timeGrainHint :: Maybe Text
  , orderingHint :: Maybe OrderingHint
  , limitHint :: Maybe Int
  , comparisonEntities :: [Text]
  , singleEntityMentions :: [Text]
  , assumptions :: [Text]
  , unresolvedPieces :: [Text]
  }
  deriving (Show, Eq, Generic)

extractQueryIntent :: Text -> QueryIntent
extractQueryIntent questionText =
  QueryIntent
    { rawQuestion = questionText
    , queryShapeHints = inferredShapeHints
    , objectMentions = inferredObjects
    , metricMentions = inferredMetrics
    , dimensionMentions = inferredDimensions
    , filters = inferredFilters
    , linkedFilters = maybe [] pure inferredLinkedFilter
    , timeGrainHint = inferredTimeGrain
    , orderingHint = inferredOrdering
    , limitHint = inferredLimit
    , comparisonEntities = maybe [] fst comparisonData
    , singleEntityMentions = inferredSingleEntities
    , assumptions = inferredAssumptions
    , unresolvedPieces = inferredUnresolved
    }
  where
    loweredQuestion = T.toLower questionText
    questionTerms = questionTokens questionText
    comparisonData = extractComparisonEntities questionText
    inferredMetrics = maybeToListText (metricIntentFromTokens questionTerms)
    inferredFilters = extractFilterHints questionText questionTerms
    inferredLinkedFilter = extractTeamLinkedFilter questionText
    inferredTimeGrain =
      if mentionsMonthlyTrend loweredQuestion
        then Just "month"
        else Nothing
    inferredLimit = extractLimitHint questionTerms
    inferredOrdering = extractOrderingHint questionTerms inferredMetrics inferredTimeGrain comparisonData
    inferredObjects = inferObjectMentions loweredQuestion questionTerms comparisonData inferredLinkedFilter inferredMetrics
    inferredDimensions = inferDimensionMentions loweredQuestion inferredObjects inferredTimeGrain
    inferredShapeHints = inferShapeHints loweredQuestion inferredTimeGrain comparisonData
    inferredSingleEntities =
      case comparisonData of
        Just _ -> []
        Nothing -> extractSingleEntityMentions questionText questionTerms
    inferredAssumptions = normalizeAssumptions questionText candidateAssumptions
    candidateAssumptions =
      [ "Interpreted 'pts' as total points."
      , "Interpreted 'scoring' as total points."
      , "Interpreted 'scorer' as players ranked by total points."
      , "Interpreted 'scorers' as players ranked by total points."
      , "Interpreted 'avg points' as average points."
      , "Interpreted 'average scoring' as average points."
      ]
    inferredUnresolved =
      [ "single_entity_filter"
      | not (null inferredSingleEntities)
      ]

extractOrderingHint :: [Text] -> [Text] -> Maybe Text -> Maybe ([Text], Bool) -> Maybe OrderingHint
extractOrderingHint questionTerms inferredMetrics inferredTimeGrain maybeComparison
  | maybeComparison /= Nothing = Nothing
  | inferredTimeGrain /= Nothing = Nothing
  | any (`elem` questionTerms) ["top", "most", "highest", "best"] || "by" `elem` questionTerms || "and" `elem` questionTerms =
      Just (OrderingHint IntentDescending (listToMaybeText inferredMetrics))
  | otherwise = Nothing

extractLimitHint :: [Text] -> Maybe Int
extractLimitHint questionTerms =
  case extractKeywordIntPair "top" questionTerms of
    Just limitValue -> Just limitValue
    Nothing ->
      if any (`elem` questionTerms) ["most", "highest", "best"]
        then Just 1
        else Nothing

extractFilterHints :: Text -> [Text] -> [IntentFilter]
extractFilterHints questionText questionTerms =
  recentFilters ++ seasonFilters ++ trendFilters
  where
    recentFilters =
      case extractRecentGames questionTerms of
        Just gamesValue -> [IntentLastNGames gamesValue]
        Nothing -> []
    seasonFilters =
      case extractSeasonBundle questionText of
        Just (seasonLabel, seasonTypeLabel) ->
          [IntentExactSeason seasonLabel, IntentSeasonType seasonTypeLabel]
        Nothing -> []
    trendFilters =
      if "past" `elem` questionTerms && "year" `elem` questionTerms
        then [IntentPastYear]
        else []

extractSeasonBundle :: Text -> Maybe (Text, Text)
extractSeasonBundle questionText = do
  seasonLabel <- extractSeasonLabel questionText
  seasonTypeLabel <- extractSeasonType questionText
  pure (seasonLabel, seasonTypeLabel)

extractSeasonLabel :: Text -> Maybe Text
extractSeasonLabel questionText =
  go (questionTokens questionText)
  where
    go (firstPart : secondPart : remainingTerms)
      | T.length firstPart == 4
      , T.length secondPart == 2
      , T.all isDigitText firstPart
      , T.all isDigitText secondPart =
          Just (firstPart <> "-" <> secondPart)
      | otherwise = go (secondPart : remainingTerms)
    go _ = Nothing

extractSeasonType :: Text -> Maybe Text
extractSeasonType questionText
  | "regular season" `T.isInfixOf` lowered = Just "regular_season"
  | "playoffs" `T.isInfixOf` lowered = Just "playoffs"
  | otherwise = Nothing
  where
    lowered = T.toLower questionText

extractTeamLinkedFilter :: Text -> Maybe LinkedFilterHint
extractTeamLinkedFilter questionText = do
  (_, afterFor) <- T.breakOnAll "for " loweredQuestion `atIndex` 0
  let rawSuffix = T.drop 4 (T.toLower afterFor)
      originalSuffix = T.drop (T.length loweredQuestion - T.length rawSuffix) questionText
  teamValue <- normalizeLinkedFilterValue originalSuffix
  if T.any isDigitText teamValue && not (T.any isAlphaText teamValue)
    then Nothing
    else
      Just
        LinkedFilterHint
          { targetObject = "Team"
          , attribute = "team_name"
          , value = teamValue
          }
  where
    loweredQuestion = T.toLower questionText

normalizeLinkedFilterValue :: Text -> Maybe Text
normalizeLinkedFilterValue suffixText =
  let trimmed =
        trimTrailingConnector $
          stripLeadingArticle $
            T.strip $
              takeUntilAny
                [ " over the "
                , " in the "
                , " by "
                , " monthly "
                ]
                suffixText
   in
    if T.null trimmed
      then Nothing
      else Just trimmed

stripLeadingArticle :: Text -> Text
stripLeadingArticle rawValue
  | "the " `T.isPrefixOf` lowered = T.strip (T.drop 4 rawValue)
  | otherwise = T.strip rawValue
  where
    lowered = T.toLower rawValue

trimTrailingConnector :: Text -> Text
trimTrailingConnector rawValue =
  T.strip $
    foldl
      (\current suffix -> maybeStripSuffix suffix current)
      rawValue
      ["?", "."]

inferShapeHints :: Text -> Maybe Text -> Maybe ([Text], Bool) -> [QueryShapeHint]
inferShapeHints loweredQuestion inferredTimeGrain maybeComparison
  | maybeComparison /= Nothing = [HintComparisonQuery]
  | inferredTimeGrain /= Nothing = [HintTrendQuery]
  | "and their" `T.isInfixOf` loweredQuestion = [HintObjectQuery]
  | otherwise = [HintMetricQuery]

inferObjectMentions :: Text -> [Text] -> Maybe ([Text], Bool) -> Maybe LinkedFilterHint -> [Text] -> [Text]
inferObjectMentions loweredQuestion questionTerms maybeComparison maybeLinkedFilter inferredMetrics =
  nub $
    comparisonObjects
      ++ explicitObjects
      ++ linkedFilterObjects
      ++ inferredMetricObjects
  where
    comparisonObjects =
      case maybeComparison of
        Just _ -> if any (`elem` questionTerms) ["team", "teams"] then ["Team"] else ["Player"]
        Nothing -> []
    explicitObjects =
      concat
        [ ["Player" | any (`elem` questionTerms) ["player", "players", "scorer", "scorers"]]
        , ["Team" | any (`elem` questionTerms) ["team", "teams"] || "wins" `elem` inferredMetrics]
        ]
    linkedFilterObjects =
      case maybeLinkedFilter of
        Just _ ->
          if "players" `T.isInfixOf` loweredQuestion || "player" `T.isInfixOf` loweredQuestion
            then ["Player"]
            else []
        Nothing -> []
    inferredMetricObjects =
      if null explicitObjects && "wins" `elem` inferredMetrics
        then ["Team"]
        else []

inferDimensionMentions :: Text -> [Text] -> Maybe Text -> [Text]
inferDimensionMentions loweredQuestion objectHints inferredTimeGrain
  | inferredTimeGrain /= Nothing && not ("by team" `T.isInfixOf` loweredQuestion) = []
  | "by team" `T.isInfixOf` loweredQuestion = ["team_name"]
  | "by player" `T.isInfixOf` loweredQuestion || "by players" `T.isInfixOf` loweredQuestion = ["player_name"]
  | "and their" `T.isInfixOf` loweredQuestion =
      case listToMaybeText objectHints of
        Just "Player" -> ["player_name"]
        Just "Team" -> ["team_name"]
        _ -> []
  | otherwise =
      case listToMaybeText objectHints of
        Just "Player" -> ["player_name"]
        Just "Team" -> ["team_name"]
        _ -> []

extractComparisonEntities :: Text -> Maybe ([Text], Bool)
extractComparisonEntities questionText
  | not ("compare " `T.isPrefixOf` loweredQuestion) = Nothing
  | otherwise =
      let afterCompare = T.drop 8 questionText
          stripped = T.strip (takeUntilMetricPhrase afterCompare)
          entities = filter (not . T.null) (map T.strip (splitComparisonEntities stripped))
       in Just (entities, length entities == 2)
  where
    loweredQuestion = T.toLower questionText

takeUntilMetricPhrase :: Text -> Text
takeUntilMetricPhrase rawValue =
  takeUntilAny
    [ " scoring"
    , " pts"
    , " points"
    , " average points"
    , " average scoring"
    , " avg points"
    ]
    rawValue

splitComparisonEntities :: Text -> [Text]
splitComparisonEntities rawEntities =
  map T.strip $
    concatMap (T.splitOn " and ") (T.splitOn "," rawEntities)

extractSingleEntityMentions :: Text -> [Text] -> [Text]
extractSingleEntityMentions questionText questionTerms
  | "what" `elem` questionTerms = []
  | "trend" `elem` questionTerms || "monthly" `elem` questionTerms = []
  | any (`elem` questionTerms) ["compare", "players", "teams", "player", "team", "scorer", "scorers"] = []
  | "and their" `T.isInfixOf` loweredQuestion = []
  | " by " `T.isInfixOf` loweredQuestion = []
  | otherwise =
      case stripMetricSuffix questionText of
        Just candidate ->
          let cleaned = normalizeEntityCandidate candidate
           in
            if T.words cleaned == [] || T.length cleaned < 3
              then []
              else [cleaned]
        Nothing -> []
  where
    loweredQuestion = T.toLower questionText

stripMetricSuffix :: Text -> Maybe Text
stripMetricSuffix questionText = do
  let loweredQuestion = T.toLower questionText
      prefix =
        if "show me " `T.isPrefixOf` loweredQuestion
          then T.drop 8 questionText
          else questionText
  metricMarker <-
    listToMaybeText $
      filter (`T.isInfixOf` loweredQuestion)
        [ " average scoring"
        , " avg points"
        , " average points"
        , " scoring"
        , " pts"
        , " points"
        , " wins"
        ]
  let markerIndex = T.breakOn metricMarker (T.toLower prefix)
  if T.null (snd markerIndex)
    then Nothing
    else Just (fst (T.breakOn metricMarker prefix))

normalizeEntityCandidate :: Text -> Text
normalizeEntityCandidate rawValue =
  T.strip $
    takeUntilAny
      [" over the ", " in the ", " for the ", "?"]
      rawValue

metricIntentFromTokens :: [Text] -> Maybe Text
metricIntentFromTokens questionTerms
  | mentionsAveragePointsConcept questionTerms = Just "average_points"
  | mentionsWinsConcept questionTerms = Just "wins"
  | mentionsTotalPointsConcept questionTerms = Just "total_points"
  | otherwise = Nothing

mentionsAveragePointsConcept :: [Text] -> Bool
mentionsAveragePointsConcept questionTerms =
  any (`elem` questionTerms) ["average", "avg"]
    && any (`elem` questionTerms) ["points", "scoring"]

mentionsWinsConcept :: [Text] -> Bool
mentionsWinsConcept questionTerms =
  "wins" `elem` questionTerms

mentionsTotalPointsConcept :: [Text] -> Bool
mentionsTotalPointsConcept questionTerms =
  not (any (`elem` questionTerms) ["average", "avg"])
    && any (`elem` questionTerms) ["points", "pts", "scoring", "scorer", "scorers"]

mentionsMonthlyTrend :: Text -> Bool
mentionsMonthlyTrend loweredQuestion =
  ("monthly" `T.isInfixOf` loweredQuestion || "trend" `T.isInfixOf` loweredQuestion)
    && "past year" `T.isInfixOf` loweredQuestion

extractRecentGames :: [Text] -> Maybe Int
extractRecentGames questionTerms =
  go questionTerms
  where
    go ("last" : numberToken : unitToken : remainingTokens)
      | unitToken `elem` ["game", "games"] =
          case readPositiveInt numberToken of
            Just intValue -> Just intValue
            Nothing -> go (numberToken : unitToken : remainingTokens)
    go (_ : remainingTokens) = go remainingTokens
    go [] = Nothing

extractKeywordIntPair :: Text -> [Text] -> Maybe Int
extractKeywordIntPair keyword questionTerms =
  go questionTerms
  where
    go (currentToken : nextToken : remainingTokens)
      | currentToken == keyword =
          case readPositiveInt nextToken of
            Just intValue -> Just intValue
            Nothing -> go (nextToken : remainingTokens)
    go (_ : remainingTokens) = go remainingTokens
    go [] = Nothing

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

normalizeAssumptions :: Text -> [Text] -> [Text]
normalizeAssumptions questionText candidateAssumptions =
  foldr includeIfTriggered [] candidateAssumptions
  where
    loweredQuestion = T.toLower questionText
    includeIfTriggered assumption current
      | assumption == "Interpreted 'pts' as total points."
      , "pts" `T.isInfixOf` loweredQuestion = assumption : current
      | assumption == "Interpreted 'average scoring' as average points."
      , "average scoring" `T.isInfixOf` loweredQuestion = assumption : current
      | assumption == "Interpreted 'avg points' as average points."
      , "avg points" `T.isInfixOf` loweredQuestion = assumption : current
      | assumption == "Interpreted 'scorers' as players ranked by total points."
      , "scorers" `T.isInfixOf` loweredQuestion = assumption : current
      | assumption == "Interpreted 'scorer' as players ranked by total points."
      , "scorer" `T.isInfixOf` loweredQuestion && not ("scorers" `T.isInfixOf` loweredQuestion) = assumption : current
      | assumption == "Interpreted 'scoring' as total points."
      , "scoring" `T.isInfixOf` loweredQuestion
      , not ("average scoring" `T.isInfixOf` loweredQuestion)
      , not ("scorer" `T.isInfixOf` loweredQuestion) = assumption : current
      | otherwise = current

takeUntilAny :: [Text] -> Text -> Text
takeUntilAny markers rawValue =
  case mapMaybe (`firstBreak` rawValue) markers of
    [] -> rawValue
    indexedBreaks -> fst (minimumByLength indexedBreaks)

firstBreak :: Text -> Text -> Maybe (Text, Int)
firstBreak marker rawValue =
  let (prefix, suffix) = T.breakOn marker (T.toLower rawValue)
   in if T.null suffix
        then Nothing
        else Just (T.take (T.length prefix) rawValue, T.length prefix)

minimumByLength :: [(Text, Int)] -> (Text, Int)
minimumByLength (firstValue : remainingValues) =
  foldl
    (\current nextValue -> if snd nextValue < snd current then nextValue else current)
    firstValue
    remainingValues
minimumByLength [] = ("", 0)

maybeStripSuffix :: Text -> Text -> Text
maybeStripSuffix suffix rawValue =
  case T.stripSuffix suffix rawValue of
    Just stripped -> stripped
    Nothing -> rawValue

listToMaybeText :: [Text] -> Maybe Text
listToMaybeText values =
  case values of
    firstValue : _ -> Just firstValue
    [] -> Nothing

maybeToListText :: Maybe Text -> [Text]
maybeToListText maybeValue =
  case maybeValue of
    Just value -> [value]
    Nothing -> []

atIndex :: [a] -> Int -> Maybe a
atIndex values indexValue =
  case drop indexValue values of
    value : _ -> Just value
    [] -> Nothing

isDigitText :: Char -> Bool
isDigitText currentChar =
  currentChar >= '0' && currentChar <= '9'

isAlphaText :: Char -> Bool
isAlphaText currentChar =
  (currentChar >= 'a' && currentChar <= 'z')
    || (currentChar >= 'A' && currentChar <= 'Z')

collapseSpaces :: Text -> Text
collapseSpaces =
  T.unwords . T.words . T.map (\currentChar -> if isSpace currentChar then ' ' else currentChar)
