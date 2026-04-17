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

data OrdinaryMetricFilterFamily
  = RecentMetricWindow
  | SeasonMetricWindow

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
  case comparison metricQuery of
    Just _ | not (null (linkedFilters base)) ->
      Left "Comparison queries currently do not support linked filters."
    _ -> pure ()
  case timeGrain base of
    Just timeGrainValue -> validateTrendMetricQuery ontology factObject metricDef timeGrainValue base
    Nothing -> do
      rowObject <- requireMetricRowObject ontology factObject (dimensions base)
      filterFamily <- classifyOrdinaryMetricFilterFamily (filters base)
      validateOrdinaryMetricLinkedFilters ontology filterFamily (objectName factObject) (linkedFilters base)
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
  validateLinkedFilters ontology (coreFactObject base) (linkedFilters base)
  if hasSeasonFilters (filters base)
    then validateSeasonFilters (filters base)
    else validateMetricFilters (filters base)
  validateOptionalMetricOrder (orders base) (metrics base)

validateTrendMetricQuery :: Ontology -> Object -> OT.MetricDef -> TimeGrain -> BaseQuery -> Either Text ()
validateTrendMetricQuery ontology factObject _metricDef timeGrainValue base = do
  validateTrendFilters (filters base)
  if null (linkedFilters base)
    then pure ()
    else Left "Trend queries currently do not support linked filters."
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
  -- Temporary planner restriction. The current slices still validate exactly
  -- one selected metric instead of a broader multi-metric query model.
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
  -- Temporary planner restriction. The long-term design should allow broader
  -- dimension combinations once validation and compilation become more general.
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Query requires exactly one selected dimension."

validateMetricFilters :: [Filter] -> Either Text ()
validateMetricFilters filterValues =
  case filterValues of
    [LastNGames gamesValue] | gamesValue > 0 -> pure ()
    _ -> Left "Query requires a positive LastNGames filter."

classifyOrdinaryMetricFilterFamily :: [Filter] -> Either Text OrdinaryMetricFilterFamily
classifyOrdinaryMetricFilterFamily filterValues =
  case filterValues of
    [LastNGames gamesValue] | gamesValue > 0 -> Right RecentMetricWindow
    _ ->
      if isExactSeasonBundle filterValues
        then Right SeasonMetricWindow
        else Left "Metric queries currently require either a positive LastNGames filter or an exact season plus season type filter bundle."

isExactSeasonBundle :: [Filter] -> Bool
isExactSeasonBundle filterValues =
  case seasonFilterPair filterValues of
    Just _ -> length filterValues == 2 && all isSeasonFilter filterValues
    Nothing -> False
  where
    isSeasonFilter filterValue =
      case filterValue of
        ExactSeason _ -> True
        SeasonTypeFilter _ -> True
        _ -> False

hasSeasonFilters :: [Filter] -> Bool
hasSeasonFilters filterValues =
  any isSeasonFilter filterValues
  where
    isSeasonFilter filterValue =
      case filterValue of
        ExactSeason _ -> True
        SeasonTypeFilter _ -> True
        _ -> False

validateTrendFilters :: [Filter] -> Either Text ()
validateTrendFilters filterValues =
  case filterValues of
    [PastYear] -> pure ()
    _ -> Left "Trend queries currently require a PastYear filter."

validateSeasonFilters :: [Filter] -> Either Text ()
validateSeasonFilters filterValues =
  case seasonFilterPair filterValues of
    Just _ -> pure ()
    Nothing -> Left "Season queries currently require both an exact season label and an explicit season type."

seasonFilterPair :: [Filter] -> Maybe (Text, Text)
seasonFilterPair filterValues = do
  seasonLabel <- foldr exactSeasonFilter Nothing filterValues
  seasonTypeLabel <- foldr seasonTypeFilter Nothing filterValues
  pure (seasonLabel, seasonTypeLabel)
  where
    exactSeasonFilter filterValue currentValue =
      case filterValue of
        ExactSeason seasonLabel -> Just seasonLabel
        _ -> currentValue
    seasonTypeFilter filterValue currentValue =
      case filterValue of
        SeasonTypeFilter seasonTypeLabel -> Just seasonTypeLabel
        _ -> currentValue

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

validateOptionalMetricOrder :: [Order] -> [MetricName] -> Either Text ()
validateOptionalMetricOrder orderValues metricValues =
  case orderValues of
    [] -> pure ()
    [Desc orderMetric] ->
      case metricValues of
        [selectedMetric] | orderMetric == selectedMetric -> pure ()
        _ -> Left "Object queries require descending ordering on the selected metric when order is present."
    _ -> Left "Object queries support at most one descending order on the selected metric."

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

ensureComparisonShape :: Ontology -> Object -> Object -> [MetricName] -> [PlayerRef] -> Either Text ()
ensureComparisonShape ontology factObject rowObject metricValues playerRefs = do
  _ <- requirePath ontology (objectName factObject) (objectName rowObject)
  -- Temporary slice restriction. Comparison is still hard-capped to one
  -- planner path even though entity references are now generalized players.
  if objectName factObject /= "PlayerGame" || objectName rowObject /= "Player"
    then Left "Comparison currently supports the PlayerGame -> Player path only."
    else pure ()
  -- Temporary slice restriction. This should broaden once comparison planning
  -- can reason over governed metrics more generally.
  if metricValues /= [TotalPoints]
    then Left "Comparison currently supports total_points only."
    else pure ()
  if length playerRefs /= 2
    then Left "Comparison requires exactly two supported entities."
    else pure ()

validateLinkedFilters :: Ontology -> Text -> [LinkedFilter] -> Either Text ()
validateLinkedFilters ontology factObjectName linkedFilterValues =
  case linkedFilterValues of
    [] -> pure ()
    [linkedFilterValue] -> do
      -- Temporary slice restriction. Linked filters are intentionally narrowed
      -- to the first proof family rather than the long-term generic cross-
      -- object filter model.
      if factObjectName `elem` ["PlayerGame", "PlayerSeasonTeam"]
        then pure ()
        else Left "Linked team filters currently support PlayerGame and PlayerSeasonTeam only."
      if targetObject linkedFilterValue /= "Team"
        then Left "Linked filters currently support Team only."
        else pure ()
      if attribute linkedFilterValue /= "team_name"
        then Left "Linked filters currently support Team.team_name only."
        else pure ()
      _ <- requirePath ontology factObjectName "Team"
      targetObjectValue <- requireObject ontology "Team"
      requireAttributeKind targetObjectValue "team_name" Dimension
    _ -> Left "Query currently supports at most one linked filter."

validateOrdinaryMetricLinkedFilters :: Ontology -> OrdinaryMetricFilterFamily -> Text -> [LinkedFilter] -> Either Text ()
validateOrdinaryMetricLinkedFilters ontology filterFamily factObjectName linkedFilterValues = do
  validateLinkedFilters ontology factObjectName linkedFilterValues
  case linkedFilterValues of
    [] -> pure ()
    _ ->
      case (filterFamily, factObjectName) of
        (RecentMetricWindow, "PlayerGame") -> pure ()
        (SeasonMetricWindow, "PlayerSeasonTeam") -> pure ()
        -- Temporary planner restriction. Ordinary linked team filters are now
        -- keyed to the supported fact grain rather than post-hoc interpreter
        -- overrides, but the supported fact surfaces are still intentionally
        -- narrow in this slice.
        (RecentMetricWindow, _) -> Left "Linked team filters on recent metric queries currently support PlayerGame only."
        (SeasonMetricWindow, _) -> Left "Season-scoped linked team filters currently support PlayerSeasonTeam only."

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
  -- Temporary planner restriction. Path search is still capped at depth 2 for
  -- the current slices; revisit this once richer ontology traversal is needed.
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
    Wins -> "wins"
    Losses -> "losses"
    WinPercentage -> "win_percentage"

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
