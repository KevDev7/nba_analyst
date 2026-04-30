{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.ResultFilterGrounding
  ( groundDraftResultPredicate
  ) where

import Control.Applicative ((<|>))
import Data.Text (Text)
import qualified Data.Text as T
import qualified QueryModel.IR as QI
import qualified OntologyLayer.Types as OT
import OntologyLayer.Types (Object)
import QueryModel.SemanticConstruction.Match
import QueryModel.SemanticConstruction.MeasureMatch (bestExecutableMetricMatch, bestPublicMeasureAttributeMatch)
import QueryModel.SemanticDraft.Normalize (normalizedMeasureKey)
import QueryModel.SemanticConstruction.PredicateGrounding (combinePredicates, normalizeNumericPredicateValue, normalizePredicateOperator)
import QueryModel.SemanticDraft.Types (DraftFilter (filterField, filterOp, filterValue), DraftPredicate (..))

groundDraftResultPredicate :: Object -> OT.MetricDef -> [DraftFilter] -> Maybe DraftPredicate -> Maybe (Maybe QI.Predicate)
groundDraftResultPredicate factObjectValue selectedMetric draftFilters maybeDraftPredicate = do
  -- Canonicalize simple result_filters into the shared result-predicate tree.
  -- From this point onward, result filtering has one internal contract.
  filterPredicates <- mapM (groundDraftResultFilterPredicate factObjectValue selectedMetric) draftFilters
  directPredicateValues <-
    case maybeDraftPredicate of
      Nothing -> Just []
      Just draftPredicate -> pure <$> groundDraftPredicate factObjectValue selectedMetric draftPredicate
  Just (combinePredicates (filterPredicates <> directPredicateValues))

groundDraftResultFilterPredicate :: Object -> OT.MetricDef -> DraftFilter -> Maybe QI.Predicate
groundDraftResultFilterPredicate factObjectValue selectedMetric draftFilter = do
  rawField <- filterField draftFilter
  rawValue <- filterValue draftFilter
  opValue <- normalizePredicateOperator (filterOp draftFilter)
  groundedField <- groundResultPredicateField factObjectValue selectedMetric rawField
  groundedValue <- normalizeNumericPredicateValue (QI.PredicateScalar rawValue)
  pure (QI.PredicateLeaf groundedField opValue groundedValue)

groundDraftPredicate :: Object -> OT.MetricDef -> DraftPredicate -> Maybe QI.Predicate
groundDraftPredicate factObjectValue selectedMetric draftPredicate =
  case draftPredicate of
    DraftPredicateLeaf {draftPredicateField = rawField, draftPredicateOp = maybeRawOp, draftPredicateValue = rawValue} -> do
      opValue <- normalizePredicateOperator maybeRawOp
      groundedField <- groundResultPredicateField factObjectValue selectedMetric rawField
      groundedValue <- normalizeNumericPredicateValue rawValue
      pure (QI.PredicateLeaf groundedField opValue groundedValue)
    DraftPredicateAnd predicateValues ->
      QI.PredicateAnd <$> mapM (groundDraftPredicate factObjectValue selectedMetric) predicateValues
    DraftPredicateOr predicateValues ->
      QI.PredicateOr <$> mapM (groundDraftPredicate factObjectValue selectedMetric) predicateValues
    DraftPredicateNot predicateValue ->
      QI.PredicateNot <$> groundDraftPredicate factObjectValue selectedMetric predicateValue

groundResultPredicateField :: Object -> OT.MetricDef -> Text -> Maybe QI.PredicateField
groundResultPredicateField factObjectValue selectedMetric rawField =
  selectedMetricField selectedMetric rawField
    <|> executableMetricField factObjectValue rawField
    <|> publicMeasureAttributeField factObjectValue rawField

selectedMetricField :: OT.MetricDef -> Text -> Maybe QI.PredicateField
selectedMetricField selectedMetric rawField =
  if metricMatchScore rawField selectedMetric > 0
    then Just (resultField (metricName selectedMetric))
    else Nothing

executableMetricField :: Object -> Text -> Maybe QI.PredicateField
executableMetricField factObjectValue rawField = do
  metricValue <- bestExecutableMetricMatch rawField factObjectValue
  _ <- singleSourceMetric metricValue
  pure (resultField (metricName metricValue))

publicMeasureAttributeField :: Object -> Text -> Maybe QI.PredicateField
publicMeasureAttributeField factObjectValue rawField = do
  aggregationValue <- explicitAggregation rawField
  attributeValue <- bestPublicMeasureAttributeMatch rawField factObjectValue
  pure (resultField (aggregationValue <> "_" <> attributeName attributeValue))

resultField :: Text -> QI.PredicateField
resultField attributeValue =
  QI.PredicateField
    { QI.predicateFieldTargetObject = ""
    , QI.predicateFieldAttribute = attributeValue
    , QI.predicateLocation = QI.PredicateResultField
    , QI.predicateFieldLinkRole = Nothing
    , QI.predicateFieldLabel = Nothing
    }

singleSourceMetric :: OT.MetricDef -> Maybe Text
singleSourceMetric metricValue =
  case metricSourceAttributes metricValue of
    [sourceAttributeValue] -> Just sourceAttributeValue
    _ -> Nothing

explicitAggregation :: Text -> Maybe Text
explicitAggregation rawField =
  let fieldKey = normalizedMeasureKey rawField
   in if any (`T.isInfixOf` fieldKey) ["average", "avg", "pergame"]
        then Just "avg"
        else
          if any (`T.isInfixOf` fieldKey) ["total", "sum"]
            then Just "sum"
            else Nothing
