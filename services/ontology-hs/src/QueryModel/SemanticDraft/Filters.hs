{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Filters
  ( draftMeasurePhrases
  , draftFilterTextValue
  , requireDraftMeasure
  , requireDraftMeasureForFamily
  , requireOptionalPositiveLimit
  , requireRankingSort
  , requireResolvedComparisonEntities
  , requireTrendGrain
  ) where

import Control.Applicative ((<|>))
import Data.List (nub)
import Data.Text (Text)
import qualified Data.Text as T
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Normalize
import QueryModel.SemanticDraft.Types

requireDraftMeasure :: SemanticDraft -> Either Text Text
requireDraftMeasure draft =
  -- Ranking needs one measure phrase, like "points", "scoring", or "average points".
  requireDraftMeasureForFamily "Ranking" draft

requireDraftMeasureForFamily :: Text -> SemanticDraft -> Either Text Text
requireDraftMeasureForFamily familyName draft =
  case measure draft of
    Just rawMeasure | T.strip rawMeasure /= "" -> Right rawMeasure
    _ ->
      case measures draft of
        rawMeasure : _ | T.strip rawMeasure /= "" -> Right rawMeasure
        _ -> Left (familyName <> " drafts require at least one user-facing measure phrase.")

draftMeasurePhrases :: SemanticDraft -> [Text]
draftMeasurePhrases draft =
  dedupeMeasures $
    [ rawMeasure
    | Just rawMeasure <- [measure draft]
    , T.strip rawMeasure /= ""
    ]
      <> [ rawMeasure
         | rawMeasure <- measures draft
         , T.strip rawMeasure /= ""
         ]

dedupeMeasures :: [Text] -> [Text]
dedupeMeasures rawMeasures =
  case rawMeasures of
    [] -> []
    rawMeasure : remaining ->
      rawMeasure
        : dedupeMeasures
          [ candidate
          | candidate <- remaining
          , normalizedMeasureKey candidate /= normalizedMeasureKey rawMeasure
          ]

requireTrendGrain :: SemanticDraft -> Either Text Text
requireTrendGrain draft =
  -- Normalize user-facing calendar grain words. Custom interval buckets are
  -- intentionally out of scope until the product defines an anchor policy.
  case normalizeTrendGrain =<< (grain draft <|> Just (kind (timeWindow draft))) of
    Just trendGrain -> Right trendGrain
    Nothing ->
      Left "Could not ground trend grain. Supported calendar grains are day, week, month, and season."

requireResolvedComparisonEntities :: SemanticDraft -> Either Text [QI.EntityRef]
requireResolvedComparisonEntities draft =
  -- Python resolves raw names against DuckDB before Haskell planning.
  -- Haskell only checks that the resolved entities are distinct and usable.
  let entityValues = resolvedEntities draft
      entityIds = map QI.entityId entityValues
   in if length entityValues >= 2 && length (nub entityIds) == length entityValues
        then Right entityValues
        else Left "Comparison drafts require at least two distinct data-resolved entities."

draftFilterTextValue :: DraftFilter -> Maybe Text
draftFilterTextValue draftFilter =
  case filterValue draftFilter of
    Just (QI.FilterText textValue) -> Just textValue
    Just (QI.FilterInt intValue) -> Just (T.pack (show intValue))
    Just (QI.FilterDouble doubleValue) -> Just (T.pack (show doubleValue))
    Nothing -> Nothing

requireOptionalPositiveLimit :: Maybe Int -> Either Text (Maybe Int)
requireOptionalPositiveLimit maybeLimit =
  -- "Top N" is optional, but if present it must be positive.
  case maybeLimit of
    Nothing -> Right Nothing
    Just currentLimit
      | currentLimit > 0 -> Right (Just currentLimit)
      | otherwise -> Left "Ranking query limit must be positive when provided."

requireRankingSort :: Maybe Text -> Either Text (QI.MetricName -> QI.Order)
requireRankingSort maybeSort =
  -- Let rank questions express both "top/highest" and "bottom/lowest".
  case fmap normalizedKey maybeSort of
    Nothing -> Right QI.Desc
    Just "desc" -> Right QI.Desc
    Just "descending" -> Right QI.Desc
    Just "top" -> Right QI.Desc
    Just "highest" -> Right QI.Desc
    Just "most" -> Right QI.Desc
    Just "asc" -> Right QI.Asc
    Just "ascending" -> Right QI.Asc
    Just "bottom" -> Right QI.Asc
    Just "lowest" -> Right QI.Asc
    Just "least" -> Right QI.Asc
    _ -> Left "Could not ground ranking sort direction against the requested metric."
