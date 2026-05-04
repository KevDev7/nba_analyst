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
  , resolveRankingOrder
  , resolveRankingIntentLabel
  ) where

import Control.Applicative ((<|>))
import Data.List (nub)
import Data.Text (Text)
import qualified Data.Text as T
import qualified OntologyLayer.Types as OT
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

resolveRankingOrder :: SemanticDraft -> OT.MetricDef -> Either Text (QI.MetricName -> QI.Order)
resolveRankingOrder draft metricDef =
  -- Resolve user ranking intent after metric grounding, so quality words like
  -- "best" can use ontology metric polarity instead of a prompt-level guess.
  case normalizedRankIntent (rankIntent draft) of
    Just intentValue -> resolveRankingIntent intentValue metricDef
    Nothing -> resolveRankingSortFallback (sort draft) metricDef

resolveRankingIntentLabel :: SemanticDraft -> Maybe Text
resolveRankingIntentLabel draft =
  case normalizedRankIntent (rankIntent draft) of
    Just intentValue -> canonicalRankingIntentLabel True intentValue
    Nothing ->
      case normalizedRankIntent (sort draft) of
        Just sortValue -> canonicalRankingIntentLabel False sortValue
        Nothing -> Nothing

resolveRankingSortFallback :: Maybe Text -> OT.MetricDef -> Either Text (QI.MetricName -> QI.Order)
resolveRankingSortFallback maybeSort metricDef =
  case normalizedRankIntent maybeSort of
    Nothing -> Right QI.Desc
    Just intentValue -> resolveRankingIntent intentValue metricDef

normalizedRankIntent :: Maybe Text -> Maybe Text
normalizedRankIntent maybeValue =
  case fmap normalizedKey maybeValue of
    Just value | not (T.null value) -> Just value
    _ -> Nothing

resolveRankingIntent :: Text -> OT.MetricDef -> Either Text (QI.MetricName -> QI.Order)
resolveRankingIntent intentValue metricDef =
  case intentValue of
    "desc" -> Right QI.Desc
    "descending" -> Right QI.Desc
    "highest" -> Right QI.Desc
    "high" -> Right QI.Desc
    "most" -> Right QI.Desc
    "asc" -> Right QI.Asc
    "ascending" -> Right QI.Asc
    "lowest" -> Right QI.Asc
    "low" -> Right QI.Asc
    "fewest" -> Right QI.Asc
    "least" -> Right QI.Asc
    "best" -> Right (qualityOrder bestOrderByPolarity metricDef)
    "top" -> Right (qualityOrder bestOrderByPolarity metricDef)
    "leader" -> Right (qualityOrder bestOrderByPolarity metricDef)
    "leaders" -> Right (qualityOrder bestOrderByPolarity metricDef)
    "leaderboard" -> Right (qualityOrder bestOrderByPolarity metricDef)
    "worst" -> Right (qualityOrder worstOrderByPolarity metricDef)
    "bottom" -> Right (qualityOrder worstOrderByPolarity metricDef)
    "rank" -> Right QI.Desc
    "ranked" -> Right QI.Desc
    "ranking" -> Right QI.Desc
    _ -> Left "Could not ground ranking intent against the requested metric."

canonicalRankingIntentLabel :: Bool -> Text -> Maybe Text
canonicalRankingIntentLabel fromRankIntent intentValue =
  case intentValue of
    "highest" -> Just "highest"
    "high" -> Just "highest"
    "most" -> Just "most"
    "lowest" -> Just "lowest"
    "low" -> Just "lowest"
    "fewest" -> Just "fewest"
    "least" -> Just "fewest"
    "best" -> Just "best"
    "top" -> Just "top"
    "leader" -> Just "top"
    "leaders" -> Just "top"
    "leaderboard" -> Just "top"
    "worst" -> Just "worst"
    "bottom" -> Just "bottom"
    "rank" -> Just "ranked"
    "ranked" -> Just "ranked"
    "ranking" -> Just "ranked"
    "asc" | fromRankIntent -> Just "lowest"
    "ascending" | fromRankIntent -> Just "lowest"
    "desc" | fromRankIntent -> Just "highest"
    "descending" | fromRankIntent -> Just "highest"
    _ -> Nothing

qualityOrder :: (OT.MetricRankingPolarity -> QI.MetricName -> QI.Order) -> OT.MetricDef -> QI.MetricName -> QI.Order
qualityOrder orderForPolarity metricDef =
  orderForPolarity (OT.ranking_polarity metricDef)

bestOrderByPolarity :: OT.MetricRankingPolarity -> QI.MetricName -> QI.Order
bestOrderByPolarity polarityValue =
  case polarityValue of
    OT.HigherIsBetter -> QI.Desc
    OT.LowerIsBetter -> QI.Asc
    OT.NeutralRankingPolarity -> QI.Desc

worstOrderByPolarity :: OT.MetricRankingPolarity -> QI.MetricName -> QI.Order
worstOrderByPolarity polarityValue =
  case polarityValue of
    OT.HigherIsBetter -> QI.Asc
    OT.LowerIsBetter -> QI.Desc
    OT.NeutralRankingPolarity -> QI.Asc
