-- Purpose:
-- Map extracted phrases onto ontology-backed concepts for the live slices.
--
-- Uses:
-- - parsed question output from Interpret.hs
-- - ontology metadata
--
-- Produces:
-- - matched metric, dimension, entity, and assumption data
--
-- Next:
-- - Classify.hs

{-# LANGUAGE OverloadedStrings #-}

module QueryModel.Match where

import Data.Text (Text)
import OntologyLayer.Graph (findAttribute, findMetric, findObject)
import OntologyLayer.Types (Ontology)
import QueryModel.IR
import QueryModel.Interpret (ParsedQuestion (..))

data MatchResult = MatchResult
  { matchedMetric :: MetricName
  , matchedDimension :: Maybe DimensionName
  , matchedFactObject :: Text
  , matchedRowObject :: Maybe Text
  , matchedEntities :: [EntityName]
  , matchedComparison :: Maybe ComparisonIntent
  , matchAssumptions :: [Text]
  }
  deriving (Show, Eq)

matchQuestion :: Ontology -> ParsedQuestion -> Either Text MatchResult
matchQuestion ontology parsedQuestion = do
  (factObjectName, rowObjectName, dimensionValue) <- matchObjectsAndDimension ontology parsedQuestion
  metricValue <- matchMetric ontology factObjectName (metricPhrase parsedQuestion)
  entityValues <- matchEntities (entityPhrases parsedQuestion)
  let comparisonValue =
        if comparisonRequested parsedQuestion
          then Just (CompareEntities entityValues)
          else Nothing
      assumptionValues = metricAssumptions (metricPhrase parsedQuestion) metricValue
  if playerConceptPresent parsedQuestion || teamConceptPresent parsedQuestion || metricPhrase parsedQuestion `elem` ["scorer", "scorers"] || extractedTimeGrain parsedQuestion /= Nothing
    then
      pure
        MatchResult
          { matchedMetric = metricValue
          , matchedDimension = dimensionValue
          , matchedFactObject = factObjectName
          , matchedRowObject = rowObjectName
          , matchedEntities = entityValues
          , matchedComparison = comparisonValue
          , matchAssumptions = assumptionValues
          }
    else Left "The supported slices expect player- or team-centric questions."

matchMetric :: Ontology -> Text -> Text -> Either Text MetricName
matchMetric ontology factObjectName phrase = do
  factObject <- maybe (Left ("Object '" <> factObjectName <> "' not found in ontology.")) Right $
    findObject ontology factObjectName
  let candidateMetric =
        case phrase of
          "average points" -> Right AveragePoints
          "avg points" -> Right AveragePoints
          "average scoring" -> Right AveragePoints
          "scoring average" -> Right AveragePoints
          "points" -> Right TotalPoints
          "total points" -> Right TotalPoints
          "pts" -> Right TotalPoints
          "scoring" -> Right TotalPoints
          "scorer" -> Right TotalPoints
          "scorers" -> Right TotalPoints
          _ -> Left "The supported slices only handle points-based metrics right now."
  metricValue <- candidateMetric
  let metricKey = renderMetricName metricValue
  case findMetric factObject metricKey of
    Just _ -> Right metricValue
    Nothing -> Left ("Metric '" <> metricKey <> "' is not available in the ontology.")

matchObjectsAndDimension :: Ontology -> ParsedQuestion -> Either Text (Text, Maybe Text, Maybe DimensionName)
matchObjectsAndDimension ontology parsedQuestion
  | comparisonRequested parsedQuestion = do
      _ <- requireObject ontology "PlayerGame"
      _ <- requireObject ontology "Player"
      _ <- requireObjectAttribute ontology "Player" "player_name"
      pure ("PlayerGame", Just "Player", Just PlayerName)
  | objectRowsRequested parsedQuestion = do
      _ <- requireObject ontology "PlayerGame"
      _ <- requireObject ontology "Player"
      _ <- requireObjectAttribute ontology "Player" "player_name"
      pure ("PlayerGame", Just "Player", Just PlayerName)
  | teamConceptPresent parsedQuestion && extractedTimeGrain parsedQuestion /= Nothing = do
      _ <- requireObject ontology "TeamGame"
      _ <- requireObject ontology "Team"
      _ <- requireObjectAttribute ontology "Team" "team_name"
      pure ("TeamGame", Just "Team", Just TeamName)
  | extractedTimeGrain parsedQuestion /= Nothing = do
      _ <- requireObject ontology "TeamGame"
      _ <- requireObjectAttribute ontology "TeamGame" "game_year_month"
      pure ("TeamGame", Nothing, Nothing)
  | teamConceptPresent parsedQuestion = do
      _ <- requireObject ontology "TeamGame"
      _ <- requireObject ontology "Team"
      _ <- requireObjectAttribute ontology "Team" "team_name"
      pure ("TeamGame", Just "Team", Just TeamName)
  | otherwise = do
      _ <- requireObject ontology "PlayerGame"
      _ <- requireObject ontology "Player"
      _ <- requireObjectAttribute ontology "Player" "player_name"
      pure ("PlayerGame", Just "Player", Just PlayerName)

metricAssumptions :: Text -> MetricName -> [Text]
metricAssumptions phrase metricValue =
  case (phrase, metricValue) of
    ("pts", TotalPoints) -> ["Interpreted 'pts' as total points."]
    ("scoring", TotalPoints) -> ["Interpreted 'scoring' as total points."]
    ("scorer", TotalPoints) -> ["Interpreted 'scorer' as players ranked by total points."]
    ("scorers", TotalPoints) -> ["Interpreted 'scorers' as players ranked by total points."]
    ("avg points", AveragePoints) -> ["Interpreted 'avg points' as average points."]
    ("average scoring", AveragePoints) -> ["Interpreted 'average scoring' as average points."]
    ("scoring average", AveragePoints) -> ["Interpreted 'scoring average' as average points."]
    _ -> []

matchEntities :: [Text] -> Either Text [EntityName]
matchEntities phrases
  | any (`elem` ["tatum", "jayson"]) phrases =
      Left "Comparison currently supports Brunson and Haliburton only."
  | otherwise =
      let uniqueEntities = foldr addEntity [] phrases
       in Right uniqueEntities

addEntity :: Text -> [EntityName] -> [EntityName]
addEntity phrase entities =
  case phrase of
    "brunson" -> appendIfMissing Brunson entities
    "jalen" -> appendIfMissing Brunson entities
    "haliburton" -> appendIfMissing Haliburton entities
    "tyrese" -> appendIfMissing Haliburton entities
    _ -> entities

appendIfMissing :: Eq a => a -> [a] -> [a]
appendIfMissing value values =
  if value `elem` values then values else value : values

requireObject :: Ontology -> Text -> Either Text ()
requireObject ontology objectName =
  case findObject ontology objectName of
    Just _ -> Right ()
    Nothing -> Left ("Object '" <> objectName <> "' not found in ontology.")

requireObjectAttribute :: Ontology -> Text -> Text -> Either Text ()
requireObjectAttribute ontology objectName attributeName = do
  objectValue <- maybe (Left ("Object '" <> objectName <> "' not found in ontology.")) Right $
    findObject ontology objectName
  case findAttribute objectValue attributeName of
    Just _ -> Right ()
    Nothing -> Left ("Attribute '" <> attributeName <> "' not found on object '" <> objectName <> "'.")

renderMetricName :: MetricName -> Text
renderMetricName metricValue =
  case metricValue of
    TotalPoints -> "total_points"
    AveragePoints -> "average_points"
    GamesPlayed -> "games_played"
    PointsPer36 -> "points_per_36"
