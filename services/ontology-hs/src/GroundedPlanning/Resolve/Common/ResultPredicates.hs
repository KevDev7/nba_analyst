{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.ResultPredicates
  ( planResultPredicateTree
  , resolveBaseResultPredicate
  , resultPredicateAuxiliaryLeaves
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import Control.Applicative ((<|>))
import GroundedPlanning.Resolve.Common.Types
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (MetricDef (aggregation, executable, name, source_attributes), Object)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

resolveBaseResultPredicate :: Object -> OT.MetricDef -> Maybe Predicate -> Either Text (Maybe ResolvedResultPredicateTree)
resolveBaseResultPredicate factObject selectedMetric maybeResultPredicate =
  mapM (resolveResultPredicateTree factObject selectedMetric 1) maybeResultPredicate

resolveResultPredicateTree :: Object -> OT.MetricDef -> Int -> Predicate -> Either Text ResolvedResultPredicateTree
resolveResultPredicateTree factObject selectedMetric startIndex predicateTree =
  fst <$> resolveResultPredicateTreeFrom factObject selectedMetric startIndex predicateTree

resolveResultPredicateTreeFrom :: Object -> OT.MetricDef -> Int -> Predicate -> Either Text (ResolvedResultPredicateTree, Int)
resolveResultPredicateTreeFrom factObject selectedMetric startIndex predicateTree =
  case predicateTree of
    PredicateLeaf fieldValue operatorValue predicateValue -> do
      predicateLeaf <- resolveResultPredicateLeaf factObject selectedMetric startIndex fieldValue operatorValue predicateValue
      let nextIndex =
            if resultPredicateKey predicateLeaf == "metric_value"
              then startIndex
              else startIndex + 1
      pure (ResolvedResultPredicateLeafNode predicateLeaf, nextIndex)
    PredicateAnd predicateValues -> do
      (resolvedValues, nextIndex) <- resolveResultPredicateChildren factObject selectedMetric startIndex predicateValues
      pure (ResolvedResultPredicateAnd resolvedValues, nextIndex)
    PredicateOr predicateValues -> do
      (resolvedValues, nextIndex) <- resolveResultPredicateChildren factObject selectedMetric startIndex predicateValues
      pure (ResolvedResultPredicateOr resolvedValues, nextIndex)
    PredicateNot predicateValue -> do
      (resolvedValue, nextIndex) <- resolveResultPredicateTreeFrom factObject selectedMetric startIndex predicateValue
      pure (ResolvedResultPredicateNot resolvedValue, nextIndex)

resolveResultPredicateChildren :: Object -> OT.MetricDef -> Int -> [Predicate] -> Either Text ([ResolvedResultPredicateTree], Int)
resolveResultPredicateChildren factObject selectedMetric startIndex predicateValues =
  case predicateValues of
    [] -> pure ([], startIndex)
    predicateValue : remaining -> do
      (resolvedValue, nextIndex) <- resolveResultPredicateTreeFrom factObject selectedMetric startIndex predicateValue
      (resolvedRemaining, finalIndex) <- resolveResultPredicateChildren factObject selectedMetric nextIndex remaining
      pure (resolvedValue : resolvedRemaining, finalIndex)

resolveResultPredicateLeaf :: Object -> OT.MetricDef -> Int -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ResolvedResultPredicateLeaf
resolveResultPredicateLeaf factObject selectedMetric indexValue fieldValue operatorValue predicateValue = do
  case predicateLocation fieldValue of
    PredicateResultField -> pure ()
    PredicateRowField -> Left "Result predicate trees only support result-level predicate fields."
  resolveResultPredicateField factObject selectedMetric indexValue (predicateFieldAttribute fieldValue) operatorValue predicateValue

resolveResultPredicateField :: Object -> OT.MetricDef -> Int -> Text -> PredicateOperator -> PredicateValue -> Either Text ResolvedResultPredicateLeaf
resolveResultPredicateField factObject selectedMetric indexValue rawAttribute operatorValue predicateValue
  | rawAttribute == "metric_value" || rawAttribute == name selectedMetric =
      pure
        ResolvedResultPredicateLeaf
          { resultPredicateKey = "metric_value"
          , resultPredicateLabel = if rawAttribute == "metric_value" then name selectedMetric else rawAttribute
          , resultPredicateColumn = Nothing
          , resultPredicateAggregation = aggregation selectedMetric
          , resultPredicateOperator = operatorValue
          , resultPredicateValue = predicateValue
          }
  | otherwise =
      case resolveMetricResultField factObject indexValue rawAttribute operatorValue predicateValue of
        Just predicateLeaf -> pure predicateLeaf
        Nothing ->
          case resolveMeasureResultField factObject indexValue rawAttribute operatorValue predicateValue of
            Just predicateLeaf -> pure predicateLeaf
            Nothing -> Left ("Could not resolve result predicate field '" <> rawAttribute <> "' against the selected fact object.")

resolveMetricResultField :: Object -> Int -> Text -> PredicateOperator -> PredicateValue -> Maybe ResolvedResultPredicateLeaf
resolveMetricResultField factObject indexValue rawAttribute operatorValue predicateValue = do
  metricValue <-
    case [metricDef | metricDef <- OT.metrics factObject, executable metricDef, name metricDef == rawAttribute] of
      metricDef : _ -> Just metricDef
      [] -> Nothing
  sourceAttributeName <-
    case source_attributes metricValue of
      [sourceAttributeValue] -> Just sourceAttributeValue
      _ -> Nothing
  attributeValue <- findAttribute factObject sourceAttributeName
  if OT.kind attributeValue == OT.Measure && OT.visibility attributeValue == OT.Public
    then
      Just
        ResolvedResultPredicateLeaf
          { resultPredicateKey = indexedResultPredicateKey indexValue
          , resultPredicateLabel = name metricValue
          , resultPredicateColumn = Just (OT.source_column attributeValue)
          , resultPredicateAggregation = aggregation metricValue
          , resultPredicateOperator = operatorValue
          , resultPredicateValue = predicateValue
          }
    else Nothing

resolveMeasureResultField :: Object -> Int -> Text -> PredicateOperator -> PredicateValue -> Maybe ResolvedResultPredicateLeaf
resolveMeasureResultField factObject indexValue rawAttribute operatorValue predicateValue = do
  (aggregationValue, attributeNameValue) <- prefixedMeasureAttribute rawAttribute
  attributeValue <- findAttribute factObject attributeNameValue
  if OT.kind attributeValue == OT.Measure && OT.visibility attributeValue == OT.Public
    then
      Just
        ResolvedResultPredicateLeaf
          { resultPredicateKey = indexedResultPredicateKey indexValue
          , resultPredicateLabel = rawAttribute
          , resultPredicateColumn = Just (OT.source_column attributeValue)
          , resultPredicateAggregation = aggregationValue
          , resultPredicateOperator = operatorValue
          , resultPredicateValue = predicateValue
          }
    else Nothing

prefixedMeasureAttribute :: Text -> Maybe (Text, Text)
prefixedMeasureAttribute rawAttribute =
  fmap (\attributeValue -> ("avg", attributeValue)) (T.stripPrefix "avg_" rawAttribute)
    <|> fmap (\attributeValue -> ("avg", attributeValue)) (T.stripPrefix "average_" rawAttribute)
    <|> fmap (\attributeValue -> ("sum", attributeValue)) (T.stripPrefix "sum_" rawAttribute)
    <|> fmap (\attributeValue -> ("sum", attributeValue)) (T.stripPrefix "total_" rawAttribute)
    <|> fmap (\attributeValue -> ("identity", attributeValue)) (T.stripPrefix "identity_" rawAttribute)

indexedResultPredicateKey :: Int -> Text
indexedResultPredicateKey indexValue =
  "result_predicate_" <> T.pack (show indexValue)

resultPredicateAuxiliaryLeaves :: Maybe ResolvedResultPredicateTree -> [ResolvedResultPredicateLeaf]
resultPredicateAuxiliaryLeaves maybePredicateTree =
  case maybePredicateTree of
    Nothing -> []
    Just predicateTree ->
      [ predicateLeaf
      | predicateLeaf <- resultPredicateLeaves predicateTree
      , resultPredicateKey predicateLeaf /= "metric_value"
      ]

resultPredicateLeaves :: ResolvedResultPredicateTree -> [ResolvedResultPredicateLeaf]
resultPredicateLeaves predicateTree =
  case predicateTree of
    ResolvedResultPredicateLeafNode predicateLeaf -> [predicateLeaf]
    ResolvedResultPredicateAnd predicateValues -> concatMap resultPredicateLeaves predicateValues
    ResolvedResultPredicateOr predicateValues -> concatMap resultPredicateLeaves predicateValues
    ResolvedResultPredicateNot predicateValue -> resultPredicateLeaves predicateValue

planResultPredicateTree :: ResolvedResultPredicateTree -> Predicate
planResultPredicateTree predicateTree =
  case predicateTree of
    ResolvedResultPredicateLeafNode predicateLeaf ->
      PredicateLeaf
        PredicateField
          { predicateFieldTargetObject = ""
          , predicateFieldAttribute = resultPredicateLabel predicateLeaf
          , predicateLocation = PredicateResultField
          , predicateFieldLinkRole = Nothing
          , predicateFieldLabel = Nothing
          }
        (resultPredicateOperator predicateLeaf)
        (resultPredicateValue predicateLeaf)
    ResolvedResultPredicateAnd predicateValues ->
      PredicateAnd (map planResultPredicateTree predicateValues)
    ResolvedResultPredicateOr predicateValues ->
      PredicateOr (map planResultPredicateTree predicateValues)
    ResolvedResultPredicateNot predicateValue ->
      PredicateNot (planResultPredicateTree predicateValue)
