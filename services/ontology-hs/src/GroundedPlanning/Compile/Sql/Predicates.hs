{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Predicates
  ( renderPredicateCondition
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common.Primitives (renderFilterLiteral, renderLikeContainsLiteral)
import QueryModel.IR (FilterValue (FilterText), PredicateOperator (..), PredicateValue (..))

renderPredicateCondition :: Text -> PredicateOperator -> PredicateValue -> Maybe Text
renderPredicateCondition columnRef operatorValue predicateValue =
  case (operatorValue, predicateValue) of
    (PredicateEquals, PredicateScalar scalarValue) ->
      Just (columnRef <> " = " <> renderFilterLiteral scalarValue)
    (PredicateNotEquals, PredicateScalar scalarValue) ->
      Just (columnRef <> " <> " <> renderFilterLiteral scalarValue)
    (PredicateGreaterThan, PredicateScalar scalarValue) ->
      Just (columnRef <> " > " <> renderFilterLiteral scalarValue)
    (PredicateGreaterThanOrEqual, PredicateScalar scalarValue) ->
      Just (columnRef <> " >= " <> renderFilterLiteral scalarValue)
    (PredicateLessThan, PredicateScalar scalarValue) ->
      Just (columnRef <> " < " <> renderFilterLiteral scalarValue)
    (PredicateLessThanOrEqual, PredicateScalar scalarValue) ->
      Just (columnRef <> " <= " <> renderFilterLiteral scalarValue)
    (PredicateIn, PredicateList values) ->
      Just (columnRef <> " IN (" <> T.intercalate ", " (map renderFilterLiteral values) <> ")")
    (PredicateNotIn, PredicateList values) ->
      Just (columnRef <> " NOT IN (" <> T.intercalate ", " (map renderFilterLiteral values) <> ")")
    (PredicateBetween, PredicateRange lowerValue upperValue) ->
      Just (columnRef <> " BETWEEN " <> renderFilterLiteral lowerValue <> " AND " <> renderFilterLiteral upperValue)
    (PredicateContains, PredicateScalar (FilterText textValue)) ->
      Just (columnRef <> " ILIKE " <> renderLikeContainsLiteral textValue <> " ESCAPE '\\'")
    _ -> Nothing
