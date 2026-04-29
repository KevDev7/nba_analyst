{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Orders
  ( orderMetricName
  , validateMetricOrders
  , validateOptionalMetricOrder
  , validateTrendOrders
  ) where

import Data.Text (Text)
import QueryModel.IR

validateMetricOrders :: Maybe ComparisonIntent -> [Order] -> [MetricName] -> Either Text ()
validateMetricOrders maybeComparison orderValues metricValues =
  case maybeComparison of
    Just _ ->
      if null orderValues
        then pure ()
        else Left "Comparison queries should not request ranking order."
    Nothing ->
      case (orderValues, metricValues) of
        ([orderValue], selectedMetric : _) | orderMetricName orderValue == selectedMetric -> pure ()
        _ -> Left "Ranking queries require ordering by the selected metric."

orderMetricName :: Order -> MetricName
orderMetricName orderValue =
  case orderValue of
    Asc metricNameValue -> metricNameValue
    Desc metricNameValue -> metricNameValue

validateOptionalMetricOrder :: [Order] -> [MetricName] -> Either Text ()
validateOptionalMetricOrder orderValues metricValues =
  case orderValues of
    [] -> pure ()
    [Desc orderMetric] ->
      case metricValues of
        selectedMetric : _ | orderMetric == selectedMetric -> pure ()
        _ -> Left "Object queries require descending ordering on the selected metric when order is present."
    [Asc orderMetric] ->
      case metricValues of
        selectedMetric : _ | orderMetric == selectedMetric -> pure ()
        _ -> Left "Object queries require ordering on the selected metric when order is present."
    _ -> Left "Object queries support at most one order on the selected metric."

validateTrendOrders :: [Order] -> Either Text ()
validateTrendOrders orderValues =
  if null orderValues
    then pure ()
    else Left "Trend queries do not accept explicit ordering."
