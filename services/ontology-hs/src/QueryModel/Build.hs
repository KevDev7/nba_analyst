-- Purpose:
-- Build the typed Query IR from parsed and matched inputs.
--
-- Uses:
-- - parsed question output from Interpret.hs
-- - matched ontology concepts from Match.hs
-- - top-level classification from Classify.hs
--
-- Produces:
-- - a typed Query IR
--
-- Next:
-- - GroundedPlanning/Validation.hs

{-# LANGUAGE OverloadedStrings #-}

module QueryModel.Build where

import Data.Text (Text)
import QueryModel.Classify (QueryKind (..))
import QueryModel.IR
import QueryModel.Interpret (ParsedQuestion (..), TimeGrainPhrase (Monthly))
import QueryModel.Match (MatchResult (..))

buildQuery :: QueryKind -> ParsedQuestion -> MatchResult -> Either Text Query
buildQuery queryKind parsedQuestion matched =
  case queryKind of
    MetricQueryKind -> Right (buildMetricQuery parsedQuestion matched)
    ObjectQueryKind -> Right (buildObjectQuery parsedQuestion matched)

buildMetricQuery :: ParsedQuestion -> MatchResult -> Query
buildMetricQuery parsedQuestion matched =
  MetricQuery
    MetricQuerySpec
      { sharedQuery =
          BaseQuery
            { coreFactObject = matchedFactObject matched
            , metrics = [matchedMetric matched]
            , dimensions = maybe [] (\dimensionValue -> [dimensionValue]) (matchedDimension matched)
            , timeGrain = renderTimeGrain <$> extractedTimeGrain parsedQuestion
            , filters = metricFilters parsedQuestion
            , orders =
                if comparisonRequested parsedQuestion || extractedTimeGrain parsedQuestion /= Nothing
                  then []
                  else [Desc (matchedMetric matched)]
            , limit =
                if comparisonRequested parsedQuestion || extractedTimeGrain parsedQuestion /= Nothing
                  then Nothing
                  else extractedLimit parsedQuestion
            , assumptions = matchAssumptions matched
            }
      , entityFilters = matchedEntities matched
      , comparison = matchedComparison matched
      }

buildObjectQuery :: ParsedQuestion -> MatchResult -> Query
buildObjectQuery parsedQuestion matched =
  ObjectQuery
    ObjectQuerySpec
      { sharedQuery =
          BaseQuery
            { coreFactObject = matchedFactObject matched
            , metrics = [matchedMetric matched]
            , dimensions = maybe [] (\dimensionValue -> [dimensionValue]) (matchedDimension matched)
            , timeGrain = Nothing
            , filters = metricFilters parsedQuestion
            , orders = [Desc (matchedMetric matched)]
            , limit = extractedLimit parsedQuestion
            , assumptions = matchAssumptions matched
            }
      , rowObject =
          case matchedRowObject matched of
            Just rowObjectValue -> rowObjectValue
            Nothing -> error "Object queries require a matched row object."
      }

metricFilters :: ParsedQuestion -> [Filter]
metricFilters parsedQuestion =
  if extractedPastYear parsedQuestion
    then [PastYear]
    else
      case extractedWindowGames parsedQuestion of
        Just windowValue -> [LastNGames windowValue]
        Nothing -> []

renderTimeGrain :: TimeGrainPhrase -> TimeGrain
renderTimeGrain timeGrainPhrase =
  case timeGrainPhrase of
    Monthly -> Month
