-- Purpose:
-- Validate the typed Query IR against the live ontology usage.
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
import OntologyLayer.Types (Attribute (kind), AttributeKind (Dimension, Measure, PrimaryKey), Link, MetricDef (executable, name, source_attributes), Object, Ontology)
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
          MetricQuerySpec currentBase _ _ -> currentBase
  playerGameObject <- requireObject ontology (coreFactObject base)
  playerObject <- requireObject ontology "Player"
  _link <- requireLink ontology "PlayerGame" "Player"
  requireAttributeKind playerGameObject "player_game_id" PrimaryKey
  requireAttributeKind playerGameObject "points" Measure
  requireAttributeKind playerGameObject "game_date" Dimension
  requireAttributeKind playerObject "player_name" Dimension
  selectedMetric <-
    case metrics base of
      [metricValue] -> Right metricValue
      _ -> Left "MetricQuery requires exactly one selected metric."
  metricDef <- requireMetric playerGameObject (metricKey selectedMetric)
  if not (executable metricDef)
    then Left ("Metric '" <> name metricDef <> "' is present in the ontology but not executable in this slice.")
    else Right ()
  case dimensions base of
    [PlayerName] -> pure ()
    _ -> Left "MetricQuery currently supports player_name as the displayed dimension."
  case filters base of
    [LastNGames gamesValue] | gamesValue > 0 -> pure ()
    _ -> Left "MetricQuery requires a positive LastNGames filter."
  case comparison metricQuery of
    Just (CompareEntities entities) -> do
      if metrics base /= [TotalPoints]
        then Left "Comparison currently supports total_points only."
        else pure ()
      if length entities /= 2
        then Left "Comparison requires exactly two supported entities."
        else pure ()
      if not (null (orders base))
        then Left "Comparison queries should not request ranking order."
        else pure ()
    Nothing ->
      case orders base of
        [Desc metricValue] | metricValue == selectedMetric -> pure ()
        _ -> Left "Ranking MetricQuery requires descending ordering by the selected metric."
  validateMetricAttributes metricDef

validateObjectQuery :: Ontology -> ObjectQuerySpec -> Either Text ()
validateObjectQuery ontology objectQuery = do
  let base =
        case objectQuery of
          ObjectQuerySpec currentBase _ -> currentBase
  playerGameObject <- requireObject ontology (coreFactObject base)
  playerObject <- requireObject ontology (rowObject objectQuery)
  _link <- requireLink ontology "PlayerGame" "Player"
  requireAttributeKind playerObject "person_id" PrimaryKey
  requireAttributeKind playerObject "player_name" Dimension
  requireAttributeKind playerGameObject "team" Dimension
  requireAttributeKind playerGameObject "game_date" Dimension
  requireAttributeKind playerGameObject "points" Measure
  metricDef <- requireMetric playerGameObject "total_points"
  if not (executable metricDef)
    then Left "ObjectQuery requires an executable total_points metric."
    else pure ()
  case dimensions base of
    [PlayerName] -> pure ()
    _ -> Left "ObjectQuery currently supports player_name rows."
  case metrics base of
    [TotalPoints] -> pure ()
    _ -> Left "ObjectQuery currently supports attached total_points only."
  case filters base of
    [LastNGames gamesValue] | gamesValue > 0 -> pure ()
    _ -> Left "ObjectQuery requires a positive LastNGames filter."
  case orders base of
    [Desc TotalPoints] -> pure ()
    _ -> Left "ObjectQuery currently requires descending total_points ordering."
  validateMetricAttributes metricDef

validateMetricAttributes :: MetricDef -> Either Text ()
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

requireMetric :: Object -> Text -> Either Text MetricDef
requireMetric object metricNameValue =
  maybe (Left ("Metric '" <> metricNameValue <> "' not found in ontology.")) Right $
    findMetric object metricNameValue

requireAttributeKind :: Object -> Text -> AttributeKind -> Either Text ()
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
