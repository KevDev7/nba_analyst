{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.PredicateGrounding
  ( combinePredicates
  , normalizeNumericPredicateValue
  , normalizePredicateOperator
  , numericFilterValue
  , textFilterValue
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import qualified Data.Text.Read as TR
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Normalize (normalizedKey)

combinePredicates :: [QI.Predicate] -> Maybe QI.Predicate
combinePredicates predicateValues =
  case predicateValues of
    [] -> Nothing
    [predicateValue] -> Just predicateValue
    _ -> Just (QI.PredicateAnd predicateValues)

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
        Just "contains" -> Just QI.PredicateContains
        _ -> Nothing

textFilterValue :: QI.FilterValue -> Maybe Text
textFilterValue rawValue =
  case rawValue of
    QI.FilterText textValue
      | T.strip textValue /= "" -> Just textValue
    _ -> Nothing

numericFilterValue :: QI.FilterValue -> Maybe QI.FilterValue
numericFilterValue rawValue =
  case rawValue of
    QI.FilterInt _ -> Just rawValue
    QI.FilterDouble _ -> Just rawValue
    QI.FilterText textValue -> parseNumericText textValue

normalizeNumericPredicateValue :: QI.PredicateValue -> Maybe QI.PredicateValue
normalizeNumericPredicateValue predicateValue =
  case predicateValue of
    QI.PredicateScalar scalarValue ->
      QI.PredicateScalar <$> numericFilterValue scalarValue
    QI.PredicateList listValues ->
      QI.PredicateList <$> mapM numericFilterValue listValues
    QI.PredicateRange lowerValue upperValue ->
      QI.PredicateRange <$> numericFilterValue lowerValue <*> numericFilterValue upperValue

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
