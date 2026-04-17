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
import OntologyLayer.Graph (findAttribute, findLink, findMetric, findObject)
import OntologyLayer.Types (Attribute (kind), AttributeKind (Dimension), Link, MetricDef (executable, name, source_attributes), Object, Ontology)
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
  rowObject <- requireMetricRowObject ontology factObject (dimensions base)
  metricDef <- requireSelectedMetric factObject (metrics base)
  validateMetricFilters (filters base)
  validateMetricAttributes metricDef
  validateMetricOrders (comparison metricQuery) (orders base) (metrics base)
  case comparison metricQuery of
    Just (CompareEntities entities) -> do
      ensureComparisonShape factObject rowObject (metrics base) entities
      pure ()
    Nothing -> pure ()

validateObjectQuery :: Ontology -> ObjectQuerySpec -> Either Text ()
validateObjectQuery ontology objectQuery = do
  let base =
        case objectQuery of
          ObjectQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  let rowObjectName = rowObject objectQuery
  _ <- requireObject ontology rowObjectName
  _ <- requireLink ontology (coreFactObject base) rowObjectName
  _ <- requireSelectedMetric factObject (metrics base)
  rowObjectValue <- requireObject ontology rowObjectName
  requireSelectedDimension rowObjectValue (dimensions base)
  validateMetricFilters (filters base)
  case metrics base of
    [TotalPoints] -> pure ()
    _ -> Left "ObjectQuery currently supports attached total_points only."
  case orders base of
    [Desc TotalPoints] -> pure ()
    _ -> Left "ObjectQuery currently requires descending total_points ordering."

requireMetricRowObject :: Ontology -> Object -> [DimensionName] -> Either Text Object
requireMetricRowObject ontology factObject dimensionValues = do
  dimensionName <- requireSingleDimension dimensionValues
  rowObjectName <- metricRowObjectName dimensionName
  rowObject <- requireObject ontology rowObjectName
  _ <- requireLink ontology (objectName factObject) rowObjectName
  requireSelectedDimension rowObject [dimensionName]
  pure rowObject

metricRowObjectName :: DimensionName -> Either Text Text
metricRowObjectName dimensionName =
  case dimensionName of
    PlayerName -> Right "Player"
    TeamName -> Right "Team"
    _ -> Left "MetricQuery currently supports player_name or team_name as the displayed dimension."

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
  requireAttributeKind object (dimensionKey dimensionName) Dimension

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

ensureComparisonShape :: Object -> Object -> [MetricName] -> [EntityName] -> Either Text ()
ensureComparisonShape factObject rowObject metricValues entities = do
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
requireObject ontology objectName =
  maybe (Left ("Object '" <> objectName <> "' not found in ontology.")) Right $
    findObject ontology objectName

requireLink :: Ontology -> Text -> Text -> Either Text Link
requireLink ontology sourceName targetName =
  maybe (Left ("Link '" <> sourceName <> " -> " <> targetName <> "' not found in ontology.")) Right $
    findLink ontology sourceName targetName

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

dimensionKey :: DimensionName -> Text
dimensionKey dimensionValue =
  case dimensionValue of
    PlayerName -> "player_name"
    TeamName -> "team_name"
    DisplayName -> "display_name"
    Team -> "team"
    PrimaryPosition -> "primary_position"

objectName :: OT.Object -> Text
objectName objectValue =
  case objectValue of
    OT.Object {OT.name = currentName} -> currentName
