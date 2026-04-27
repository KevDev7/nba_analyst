-- Purpose:
-- Route validated Query IR into the matching grounded-planning validation family.
--
-- Uses:
-- - Query IR from the query-model step
-- - family-specific grounded-planning validators
--
-- Produces:
-- - a validation decision for grounded planning
--
-- Next:
-- - Resolve.hs

{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation (validateQuery) where

import Data.Text (Text)
import qualified GroundedPlanning.Validation.Aggregate as Aggregate
import qualified GroundedPlanning.Validation.Compare as Compare
import qualified GroundedPlanning.Validation.Find as Find
import qualified GroundedPlanning.Validation.Object as Object
import qualified GroundedPlanning.Validation.Rank as Rank
import qualified GroundedPlanning.Validation.Trend as Trend
import OntologyLayer.Types (Ontology)
import QueryModel.IR

validateQuery :: Ontology -> Query -> Either Text ()
validateQuery ontology query =
  case query of
    MetricQuery spec ->
      case comparison spec of
        Just _ -> Compare.validateCompareMetricQuery ontology spec
        Nothing ->
          case queryTimeGrain spec of
            Just _ -> Trend.validateTrendMetricQuery ontology spec
            Nothing ->
              if hasMetricOrder spec
                then Rank.validateRankMetricQuery ontology spec
                else Aggregate.validateAggregateMetricQuery ontology spec
    ObjectQuery spec -> Object.validateObjectQuery ontology spec
    FindQuery spec -> Find.validateFindQuery ontology spec

queryTimeGrain :: MetricQuerySpec -> Maybe TimeGrain
queryTimeGrain spec =
  case spec of
    MetricQuerySpec {sharedQuery = BaseQuery {timeGrain = currentTimeGrain}} -> currentTimeGrain

hasMetricOrder :: MetricQuerySpec -> Bool
hasMetricOrder spec =
  case spec of
    MetricQuerySpec {sharedQuery = BaseQuery {orders = orderValues}} -> not (null orderValues)
