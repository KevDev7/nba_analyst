{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.Types where

data OrdinaryMetricFilterFamily
  = RecentMetricWindow
  | SeasonMetricWindow

data OrdinaryLinkedFilterQueryKind
  = MetricLinkedFilterQuery
  | ObjectLinkedFilterQuery
