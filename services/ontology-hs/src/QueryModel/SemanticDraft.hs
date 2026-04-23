-- Purpose:
-- Normalize an LLM-produced semantic draft into the typed Query IR.
--
-- Uses:
-- - a deliberately loose, language-facing JSON draft
-- - the current ontology-backed IR constructors
--
-- Produces:
-- - QueryModel.IR.Query for grounded planning
--
-- Next:
-- - GroundedPlanning.Validation

{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft
  ( SemanticDraft
  , semanticDraftToQuery
  ) where

import Data.Aeson (FromJSON (parseJSON), withObject, (.:), (.:?), (.!=))
import Data.Text (Text)
import qualified Data.Text as T
import qualified QueryModel.IR as QI

data DraftTimeWindow = DraftTimeWindow
  { kind :: Text
  , value :: Int
  }
  deriving (Show, Eq)

instance FromJSON DraftTimeWindow where
  parseJSON = withObject "DraftTimeWindow" $ \obj ->
    DraftTimeWindow
      <$> obj .: "kind"
      <*> obj .: "value"

data SemanticDraft = SemanticDraft
  { task :: Text
  , subject :: Text
  , measure :: Text
  , timeWindow :: DraftTimeWindow
  , limit :: Maybe Int
  , sort :: Maybe Text
  , assumptions :: [Text]
  }
  deriving (Show, Eq)

instance FromJSON SemanticDraft where
  parseJSON = withObject "SemanticDraft" $ \obj ->
    SemanticDraft
      <$> obj .: "task"
      <*> obj .: "subject"
      <*> obj .: "measure"
      <*> obj .: "time_window"
      <*> obj .:? "limit"
      <*> obj .:? "sort"
      <*> obj .:? "assumptions" .!= []

semanticDraftToQuery :: SemanticDraft -> Either Text QI.Query
semanticDraftToQuery draft = do
  requireRankTask (task draft)
  requirePlayerSubject (subject draft)
  requirePointsMeasure (measure draft)
  gamesValue <- requireLastNGamesWindow (timeWindow draft)
  limitValue <- requireOptionalPositiveLimit (limit draft)
  requireDescendingSort (sort draft)
  pure (playerRecentPointsRankingQuery gamesValue limitValue (assumptions draft))

requireRankTask :: Text -> Either Text ()
requireRankTask rawTask =
  if normalize rawTask `elem` ["rank", "ranking", "top"]
    then Right ()
    else Left "Slice 36 only supports ranking player points over the last N games."

requirePlayerSubject :: Text -> Either Text ()
requirePlayerSubject rawSubject =
  if normalize rawSubject `elem` ["player", "players"]
    then Right ()
    else Left "Slice 36 only supports player rankings."

requirePointsMeasure :: Text -> Either Text ()
requirePointsMeasure rawMeasure =
  if normalize rawMeasure `elem` ["point", "points", "pts", "scoring"]
    then Right ()
    else Left "Slice 36 only supports points/scoring as the measure."

requireLastNGamesWindow :: DraftTimeWindow -> Either Text Int
requireLastNGamesWindow window =
  if normalize (kind window) == "last_n_games" && value window > 0
    then Right (value window)
    else Left "Slice 36 requires a positive last_n_games time window."

requireOptionalPositiveLimit :: Maybe Int -> Either Text (Maybe Int)
requireOptionalPositiveLimit maybeLimit =
  case maybeLimit of
    Nothing -> Right Nothing
    Just limitValue
      | limitValue > 0 -> Right (Just limitValue)
      | otherwise -> Left "Slice 36 requires limit to be positive when provided."

requireDescendingSort :: Maybe Text -> Either Text ()
requireDescendingSort maybeSort =
  case fmap normalize maybeSort of
    Nothing -> Right ()
    Just "desc" -> Right ()
    Just "descending" -> Right ()
    _ -> Left "Slice 36 only supports descending ranking."

playerRecentPointsRankingQuery :: Int -> Maybe Int -> [Text] -> QI.Query
playerRecentPointsRankingQuery gamesValue maybeLimit assumptionValues =
  QI.MetricQuery
    QI.MetricQuerySpec
      { QI.sharedQuery =
          QI.BaseQuery
            { QI.coreFactObject = "PlayerGame"
            , QI.metrics = ["total_points"]
            , QI.dimensions = ["full_name"]
            , QI.timeGrain = Nothing
            , QI.filters = [QI.lastNGamesFilter gamesValue]
            , QI.linkedFilters = []
            , QI.orders = [QI.Desc "total_points"]
            , QI.limit = maybeLimit
            , QI.assumptions = assumptionValues
            }
      , QI.entityFilters = []
      , QI.comparison = Nothing
      }

normalize :: Text -> Text
normalize =
  T.toLower . T.strip
