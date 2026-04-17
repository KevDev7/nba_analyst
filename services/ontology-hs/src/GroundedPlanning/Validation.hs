-- Purpose:
-- Validate the typed Query IR against the generated semantic ontology.
--
-- Uses:
-- - typed ontology values
-- - Query IR from the query-model step
--
-- Produces:
-- - a validation decision for grounded planning
--
-- Next:
-- - Resolve.hs

{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation where

import Data.Text (Text)
import OntologyLayer.Graph (DiscoveredPath, findAttribute, findMetric, findObject, findPath, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (Attribute (kind), AttributeKind (Dimension), MetricDef (executable, name, source_attributes), Object, Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validateQuery :: Ontology -> Query -> Either Text ()
validateQuery ontology query =
  case query of
    MetricQuery spec -> validateMetricQuery ontology spec
    ObjectQuery spec -> validateObjectQuery ontology spec

validateMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ()
validateMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  metricDef <- requireSelectedMetric factObject (metrics base)
  validateMetricAttributes metricDef
  case timeGrain base of
    Just timeGrainValue -> validateTrendMetricQuery ontology factObject metricDef timeGrainValue base
    Nothing -> do
      rowObject <- requireMetricRowObject ontology factObject (dimensions base)
      validateRankingFilters (filters base)
      validateMetricOrders (comparison metricQuery) (orders base) (metrics base)
      case comparison metricQuery of
        Just (CompareEntities entities) -> ensureComparisonShape ontology factObject rowObject (metrics base) entities
        Nothing -> pure ()

validateObjectQuery :: Ontology -> ObjectQuerySpec -> Either Text ()
validateObjectQuery ontology objectQuery = do
  let base =
        case objectQuery of
          ObjectQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  let rowObjectNameValue = rowObject objectQuery
  _ <- requirePath ontology (objectName factObject) rowObjectNameValue
  _ <- requireSelectedMetric factObject (metrics base)
  rowObjectValue <- requireObject ontology rowObjectNameValue
  requireSelectedDimension rowObjectValue (dimensions base)
  validateMetricFilters (filters base)
  case metrics base of
    [TotalPoints] -> pure ()
    _ -> Left "ObjectQuery currently supports attached total_points only."
  case orders base of
    [Desc TotalPoints] -> pure ()
    _ -> Left "ObjectQuery currently requires descending total_points ordering."

validateTrendMetricQuery :: Ontology -> Object -> OT.MetricDef -> TimeGrain -> BaseQuery -> Either Text ()
validateTrendMetricQuery ontology factObject _metricDef timeGrainValue base = do
  validateTrendFilters (filters base)
  validateTrendDimensions ontology factObject (dimensions base)
  validateTrendOrders (orders base)
  case timeGrainValue of
    Month -> requireAttributeKind factObject "game_year_month" Dimension

requireMetricRowObject :: Ontology -> Object -> [DimensionName] -> Either Text Object
requireMetricRowObject ontology factObject dimensionValues = do
  dimensionName <- requireSingleDimension dimensionValues
  rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionName
  requireSelectedDimension rowObject [dimensionName]
  pure rowObject

requireReachableDimensionObject :: Ontology -> Text -> DimensionName -> Either Text Object
requireReachableDimensionObject ontology factObjectName dimensionName = do
  attributeName <- dimensionKey dimensionName
  case firstLinkedObjectWithAttribute ontology factObjectName attributeName of
    Just objectValue -> Right objectValue
    Nothing ->
      case objectWithAttribute ontology factObjectName attributeName of
        Just objectValue -> Right objectValue
        Nothing ->
          Left
            ( "No valid ontology path from '"
                <> factObjectName
                <> "' reaches a displayed dimension attribute '"
                <> attributeName
                <> "'."
            )

firstLinkedObjectWithAttribute :: Ontology -> Text -> Text -> Maybe Object
firstLinkedObjectWithAttribute ontology factObjectName attributeName =
  case
    [ objectValue
    | discoveredPath <- findPathsFrom ontology 2 factObjectName
    , Just objectValue <- [findObject ontology (OG.targetObjectName discoveredPath)]
    , hasAttribute objectValue attributeName
    ]
    of
    objectValue : _ -> Just objectValue
    [] -> Nothing

objectWithAttribute :: Ontology -> Text -> Text -> Maybe Object
objectWithAttribute ontology objectNameValue attributeName = do
  objectValue <- findObject ontology objectNameValue
  if hasAttribute objectValue attributeName
    then Just objectValue
    else Nothing

hasAttribute :: Object -> Text -> Bool
hasAttribute objectValue attributeName =
  case findAttribute objectValue attributeName of
    Just _ -> True
    Nothing -> False

requireSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireSelectedMetric factObject metricValues =
  case metricValues of
    [metricValue] -> do
      metricDef <- requireMetric factObject (metricKey metricValue)
      if executable metricDef
        then pure metricDef
        else Left ("Metric '" <> name metricDef <> "' is present in the ontology but not executable in this slice.")
    _ -> Left "Query requires exactly one selected metric."

requireSelectedDimension :: Object -> [DimensionName] -> Either Text ()
requireSelectedDimension object dimensionValues = do
  dimensionName <- requireSingleDimension dimensionValues
  attributeName <- dimensionKey dimensionName
  requireAttributeKind object attributeName Dimension

requireSingleDimension :: [DimensionName] -> Either Text DimensionName
requireSingleDimension dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Query requires exactly one selected dimension."

validateMetricFilters :: [Filter] -> Either Text ()
validateMetricFilters filterValues =
  case filterValues of
    [LastNGames gamesValue] | gamesValue > 0 -> pure ()
    _ -> Left "Query requires a positive LastNGames filter."

validateRankingFilters :: [Filter] -> Either Text ()
validateRankingFilters = validateMetricFilters

validateTrendFilters :: [Filter] -> Either Text ()
validateTrendFilters filterValues =
  case filterValues of
    [PastYear] -> pure ()
    _ -> Left "Trend queries currently require a PastYear filter."

validateMetricOrders :: Maybe ComparisonIntent -> [Order] -> [MetricName] -> Either Text ()
validateMetricOrders maybeComparison orderValues metricValues =
  case maybeComparison of
    Just _ ->
      if null orderValues
        then pure ()
        else Left "Comparison queries should not request ranking order."
    Nothing ->
      case (orderValues, metricValues) of
        ([Desc orderMetric], [selectedMetric]) | orderMetric == selectedMetric -> pure ()
        _ -> Left "Ranking queries require descending ordering by the selected metric."

validateTrendOrders :: [Order] -> Either Text ()
validateTrendOrders orderValues =
  if null orderValues
    then pure ()
    else Left "Trend queries currently do not accept explicit ordering."

validateTrendDimensions :: Ontology -> Object -> [DimensionName] -> Either Text ()
validateTrendDimensions ontology factObject dimensionValues =
  case dimensionValues of
    [] -> pure ()
    [dimensionValue] -> do
      rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionValue
      requireSelectedDimension rowObject [dimensionValue]
      pure ()
    _ -> Left "Trend queries currently support at most one business grouping dimension."

ensureComparisonShape :: Ontology -> Object -> Object -> [MetricName] -> [EntityName] -> Either Text ()
ensureComparisonShape ontology factObject rowObject metricValues entities = do
  _ <- requirePath ontology (objectName factObject) (objectName rowObject)
  if objectName factObject /= "PlayerGame" || objectName rowObject /= "Player"
    then Left "Comparison currently supports the PlayerGame -> Player path only."
    else pure ()
  if metricValues /= [TotalPoints]
    then Left "Comparison currently supports total_points only."
    else pure ()
  if length entities /= 2
    then Left "Comparison requires exactly two supported entities."
    else pure ()

validateMetricAttributes :: OT.MetricDef -> Either Text ()
validateMetricAttributes metricDef =
  if null (source_attributes metricDef)
    then Left ("Metric '" <> name metricDef <> "' must reference at least one source attribute.")
    else Right ()

requireObject :: Ontology -> Text -> Either Text Object
requireObject ontology objectNameValue =
  maybe (Left ("Object '" <> objectNameValue <> "' not found in ontology.")) Right $
    findObject ontology objectNameValue

requirePath :: Ontology -> Text -> Text -> Either Text DiscoveredPath
requirePath ontology sourceName targetName =
  maybe
    ( Left
        ( "No valid ontology path from '"
            <> sourceName
            <> "' to '"
            <> targetName
            <> "'."
        )
    )
    Right
    (findPath ontology 2 sourceName targetName)

requireMetric :: Object -> Text -> Either Text OT.MetricDef
requireMetric object metricNameValue =
  maybe (Left ("Metric '" <> metricNameValue <> "' not found in ontology.")) Right $
    findMetric object metricNameValue

requireAttributeKind :: Object -> Text -> OT.AttributeKind -> Either Text ()
requireAttributeKind object attributeName expectedKind = do
  attribute <- maybe (Left ("Attribute '" <> attributeName <> "' not found in ontology.")) Right $
    findAttribute object attributeName
  if kind attribute == expectedKind
    then pure ()
    else Left ("Attribute '" <> attributeName <> "' has the wrong kind in the ontology.")

metricKey :: MetricName -> Text
metricKey metricValue =
  case metricValue of
    TotalPoints -> "total_points"
    AveragePoints -> "average_points"
    GamesPlayed -> "games_played"
    PointsPer36 -> "points_per_36"

dimensionKey :: DimensionName -> Either Text Text
dimensionKey dimensionValue =
  case dimensionValue of
    PlayerName -> Right "player_name"
    TeamName -> Right "team_name"
    DisplayName -> Right "display_name"
    Team -> Right "team"
    PrimaryPosition -> Right "primary_position"

objectName :: OT.Object -> Text
objectName objectValue =
  case objectValue of
    OT.Object {OT.name = currentName} -> currentName
