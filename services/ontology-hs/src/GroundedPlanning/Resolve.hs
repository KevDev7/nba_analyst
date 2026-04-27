-- Purpose:
-- Route validated Query IR into the matching grounded-planning resolution family.
--
-- Uses:
-- - validated Query IR
-- - family-specific grounded-planning resolvers
--
-- Produces:
-- - a grounded query description ready for compilation
--
-- Next:
-- - Compile.hs

{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve
  ( module GroundedPlanning.Resolve.Common
  , resolveQuery
  )
where

import qualified GroundedPlanning.Resolve.Compare as Compare
import GroundedPlanning.Resolve.Common
import qualified GroundedPlanning.Resolve.Aggregate as Aggregate
import qualified GroundedPlanning.Resolve.Find as Find
import qualified GroundedPlanning.Resolve.Object as Object
import qualified GroundedPlanning.Resolve.Rank as Rank
import qualified GroundedPlanning.Resolve.Trend as Trend
import Data.Text (Text)
import OntologyLayer.Types (Ontology)
import QueryModel.IR

resolveQuery :: Ontology -> Query -> Either Text ResolvedQuery
resolveQuery ontology query =
  case query of
    MetricQuery spec ->
      case comparison spec of
        Just _ -> ResolvedMetric <$> Compare.resolveCompareMetricQuery ontology spec
        Nothing ->
          case queryTimeGrain spec of
            Just _ -> ResolvedTrend <$> Trend.resolveTrendQuery ontology spec
            Nothing ->
              if hasMetricOrder spec
                then ResolvedMetric <$> Rank.resolveRankMetricQuery ontology spec
                else ResolvedMetric <$> Aggregate.resolveAggregateMetricQuery ontology spec
    ObjectQuery spec -> ResolvedObject <$> Object.resolveObjectQuery ontology spec
    FindQuery spec -> ResolvedFind <$> Find.resolveFindQuery ontology spec

hasMetricOrder :: MetricQuerySpec -> Bool
hasMetricOrder spec =
  case spec of
    MetricQuerySpec {sharedQuery = BaseQuery {orders = orderValues}} -> not (null orderValues)
