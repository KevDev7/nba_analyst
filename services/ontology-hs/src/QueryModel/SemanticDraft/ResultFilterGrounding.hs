{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.ResultFilterGrounding
  ( groundDraftResultPredicate
  ) where

import Control.Applicative ((<|>))
import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Read as TR
import qualified QueryModel.IR as QI
import qualified OntologyLayer.Types as OT
import OntologyLayer.Types (Object)
import QueryModel.SemanticDraft.Match
import QueryModel.SemanticDraft.MeasureMatch (bestExecutableMetricMatch, bestPublicMeasureAttributeMatch)
import QueryModel.SemanticDraft.Normalize (normalizedKey, normalizedMeasureKey)
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

combinePredicates :: [QI.Predicate] -> Maybe QI.Predicate
combinePredicates predicateValues =
  case predicateValues of
    [] -> Nothing
    [predicateValue] -> Just predicateValue
    _ -> Just (QI.PredicateAnd predicateValues)

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

numericResultValue :: QI.FilterValue -> Maybe QI.FilterValue
numericResultValue rawValue =
  case rawValue of
    QI.FilterInt _ -> Just rawValue
    QI.FilterDouble _ -> Just rawValue
    QI.FilterText textValue -> parseNumericText textValue

parseNumericText :: Text -> Maybe QI.FilterValue
parseNumericText rawValue =
  case TR.signed TR.decimal strippedValue of
    Right (intValue, remaining) | T.strip remaining == "" -> Just (QI.FilterInt intValue)
    _ ->
      case TR.signed TR.double doubleReadyValue of
        Right (doubleValue, remaining) | T.strip remaining == "" -> Just (QI.FilterDouble doubleValue)
        _ -> Nothing
  where
    strippedValue = T.strip rawValue
    doubleReadyValue =
      case T.uncons strippedValue of
        Just ('.', _) -> "0" <> strippedValue
        Just ('-', rest) ->
          case T.uncons rest of
            Just ('.', _) -> "-0" <> rest
            _ -> strippedValue
        _ -> strippedValue

normalizePredicateOperator :: Maybe Text -> Maybe QI.PredicateOperator
normalizePredicateOperator maybeRawOp =
  case T.strip <$> maybeRawOp of
    Just "=" -> Just QI.PredicateEquals
    Just "!=" -> Just QI.PredicateNotEquals
    Just "<>" -> Just QI.PredicateNotEquals
    Just ">" -> Just QI.PredicateGreaterThan
    Just ">=" -> Just QI.PredicateGreaterThanOrEqual
    Just "<" -> Just QI.PredicateLessThan
    Just "<=" -> Just QI.PredicateLessThanOrEqual
    _ ->
      case normalizedKey <$> maybeRawOp of
        Nothing -> Just QI.PredicateEquals
        Just "" -> Just QI.PredicateEquals
        Just "eq" -> Just QI.PredicateEquals
        Just "equals" -> Just QI.PredicateEquals
        Just "is" -> Just QI.PredicateEquals
        Just "notequals" -> Just QI.PredicateNotEquals
        Just "not" -> Just QI.PredicateNotEquals
        Just "neq" -> Just QI.PredicateNotEquals
        Just "over" -> Just QI.PredicateGreaterThan
        Just "above" -> Just QI.PredicateGreaterThan
        Just "greaterthan" -> Just QI.PredicateGreaterThan
        Just "gt" -> Just QI.PredicateGreaterThan
        Just "morethan" -> Just QI.PredicateGreaterThan
        Just "atleast" -> Just QI.PredicateGreaterThanOrEqual
        Just "gte" -> Just QI.PredicateGreaterThanOrEqual
        Just "under" -> Just QI.PredicateLessThan
        Just "below" -> Just QI.PredicateLessThan
        Just "lessthan" -> Just QI.PredicateLessThan
        Just "lt" -> Just QI.PredicateLessThan
        Just "atmost" -> Just QI.PredicateLessThanOrEqual
        Just "lte" -> Just QI.PredicateLessThanOrEqual
        Just "in" -> Just QI.PredicateIn
        Just "notin" -> Just QI.PredicateNotIn
        Just "between" -> Just QI.PredicateBetween
        _ -> Nothing

normalizeNumericPredicateValue :: QI.PredicateValue -> Maybe QI.PredicateValue
normalizeNumericPredicateValue predicateValue =
  case predicateValue of
    QI.PredicateScalar scalarValue ->
      QI.PredicateScalar <$> numericResultValue scalarValue
    QI.PredicateList listValues ->
      QI.PredicateList <$> mapM numericResultValue listValues
    QI.PredicateRange lowerValue upperValue ->
      QI.PredicateRange <$> numericResultValue lowerValue <*> numericResultValue upperValue
