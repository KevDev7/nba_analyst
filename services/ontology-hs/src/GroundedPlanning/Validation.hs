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

import Control.Applicative ((<|>))
import Data.List (nub)
import Data.Text (Text)
import OntologyLayer.Graph (DiscoveredPath, findAttribute, findMetric, findObject, findPath, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (AttributeKind (Dimension), MetricDef (executable, name, source_attributes), Object, Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

data OrdinaryMetricFilterFamily
  = RecentMetricWindow
  | SeasonMetricWindow

data OrdinaryLinkedFilterQueryKind
  = MetricLinkedFilterQuery
  | ObjectLinkedFilterQuery

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
  case comparison metricQuery of
    Just (CompareEntities entities) -> do
      metricDef <- requireComparisonSelectedMetric factObject (metrics base)
      validateMetricAttributes metricDef
      rowObject <- requireComparisonRowObject ontology factObject (dimensions base)
      validateComparisonQuery ontology factObject rowObject base entities
    Nothing ->
      case timeGrain base of
        Just timeGrainValue -> do
          metricDef <- requireTrendSelectedMetric factObject (metrics base)
          validateMetricAttributes metricDef
          validateTrendMetricQuery ontology factObject metricDef timeGrainValue base
        Nothing -> do
          metricDef <- requireOrdinaryMetricSelectedMetric factObject (metrics base)
          validateMetricAttributes metricDef
          _ <- requireOrdinaryMetricRowObject ontology factObject (dimensions base)
          filterFamily <- classifyOrdinaryMetricFilterFamily (filters base)
          validateOrdinaryLinkedFilters ontology MetricLinkedFilterQuery filterFamily (objectName factObject) (linkedFilters base)
          validateMetricOrders (comparison metricQuery) (orders base) (metrics base)
          pure ()

validateObjectQuery :: Ontology -> ObjectQuerySpec -> Either Text ()
validateObjectQuery ontology objectQuery = do
  let base =
        case objectQuery of
          ObjectQuerySpec {sharedQuery = currentBase} -> currentBase
  validateObjectQueryTimeGrain (timeGrain base)
  factObject <- requireObject ontology (coreFactObject base)
  let rowObjectNameValue = rowObject objectQuery
  _ <- requirePath ontology (objectName factObject) rowObjectNameValue
  metricDef <- requireObjectQuerySelectedMetric factObject (metrics base)
  validateMetricAttributes metricDef
  rowObjectValue <- requireObject ontology rowObjectNameValue
  requireObjectQueryDimension rowObjectValue (dimensions base)
  filterFamily <- classifyOrdinaryMetricFilterFamily (filters base)
  validateOrdinaryLinkedFilters ontology ObjectLinkedFilterQuery filterFamily (objectName factObject) (linkedFilters base)
  validateOptionalMetricOrder (orders base) (metrics base)

validateTrendMetricQuery :: Ontology -> Object -> OT.MetricDef -> TimeGrain -> BaseQuery -> Either Text ()
validateTrendMetricQuery ontology factObject _metricDef timeGrainValue base = do
  validateTrendTimeGrain timeGrainValue
  validateTrendFilters (filters base)
  validateTrendLimit (limit base)
  validateTrendLinkedFilters (linkedFilters base)
  validateTrendOrders (orders base)
  validateTrendFactSurface factObject
  validateTrendDimensions ontology factObject (dimensions base)
  requireAttributeKind factObject "game_year_month" Dimension

requireOrdinaryMetricRowObject :: Ontology -> Object -> [DimensionName] -> Either Text Object
requireOrdinaryMetricRowObject ontology factObject dimensionValues = do
  dimensionName <- requireOrdinaryMetricDimension dimensionValues
  rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionName
  requireOrdinaryMetricDimensionOnObject rowObject dimensionName
  pure rowObject

requireComparisonRowObject :: Ontology -> Object -> [DimensionName] -> Either Text Object
requireComparisonRowObject ontology factObject dimensionValues = do
  dimensionName <- requireComparisonDimension dimensionValues
  rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionName
  requireComparisonDimensionOnObject rowObject dimensionName
  pure rowObject

requireReachableDimensionObject :: Ontology -> Text -> DimensionName -> Either Text Object
requireReachableDimensionObject ontology factObjectName dimensionName = do
  let attributeName = dimensionName
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

requireOrdinaryMetricSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireOrdinaryMetricSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Ranking/aggregation metric queries currently require exactly one selected metric."
    factObject
    metricValues

requireTrendSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireTrendSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Trend queries currently require exactly one selected metric."
    factObject
    metricValues

requireObjectQuerySelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireObjectQuerySelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Object queries currently require exactly one selected metric."
    factObject
    metricValues

requireComparisonSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireComparisonSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Comparison queries currently require exactly one selected metric."
    factObject
    metricValues

requireFamilySelectedMetric :: Text -> Object -> [MetricName] -> Either Text OT.MetricDef
requireFamilySelectedMetric cardinalityMessage factObject metricValues =
  case metricValues of
    [metricValue] -> do
      metricDef <- requireMetric factObject metricValue
      if executable metricDef
        then pure metricDef
        else Left ("Metric '" <> name metricDef <> "' is present in the ontology but not executable in this slice.")
    _ -> Left cardinalityMessage

requireOrdinaryMetricDimension :: [DimensionName] -> Either Text DimensionName
requireOrdinaryMetricDimension dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Ranking/aggregation metric queries currently require exactly one business grouping dimension."

requireObjectQueryDimensionName :: [DimensionName] -> Either Text DimensionName
requireObjectQueryDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Object queries currently require exactly one row dimension."

requireComparisonDimension :: [DimensionName] -> Either Text DimensionName
requireComparisonDimension dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Comparison queries currently require exactly one business grouping dimension."

requireOrdinaryMetricDimensionOnObject :: Object -> DimensionName -> Either Text ()
requireOrdinaryMetricDimensionOnObject object dimensionName = do
  let attributeName = dimensionName
  requireAttributeKind object attributeName Dimension

requireObjectQueryDimension :: Object -> [DimensionName] -> Either Text ()
requireObjectQueryDimension object dimensionValues = do
  dimensionName <- requireObjectQueryDimensionName dimensionValues
  let attributeName = dimensionName
  requireAttributeKind object attributeName Dimension

requireComparisonDimensionOnObject :: Object -> DimensionName -> Either Text ()
requireComparisonDimensionOnObject object dimensionName = do
  let attributeName = dimensionName
  requireAttributeKind object attributeName Dimension

validateMetricFilters :: [Filter] -> Either Text ()
validateMetricFilters filterValues =
  case filterValues of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue
      , gamesValue > 0 -> pure ()
    _ -> Left "Query requires a positive LastNGames filter."

classifyOrdinaryMetricFilterFamily :: [Filter] -> Either Text OrdinaryMetricFilterFamily
classifyOrdinaryMetricFilterFamily filterValues =
  case filterValues of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue
      , gamesValue > 0 -> Right RecentMetricWindow
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
      let kindValue = filterKindText filterValue
       in kindValue == "exact_season" || kindValue == "season_type"

hasSeasonFilters :: [Filter] -> Bool
hasSeasonFilters filterValues =
  any isSeasonFilter filterValues
  where
    isSeasonFilter filterValue =
      let kindValue = filterKindText filterValue
       in kindValue == "exact_season" || kindValue == "season_type"

validateTrendFilters :: [Filter] -> Either Text ()
validateTrendFilters filterValues =
  case filterValues of
    [filterValue]
      | isPastYearFilter filterValue -> pure ()
    _ -> Left "Trend queries currently require a PastYear filter."

validateTrendTimeGrain :: TimeGrain -> Either Text ()
validateTrendTimeGrain timeGrainValue =
  if timeGrainText timeGrainValue == timeGrainText monthTimeGrain
    then pure ()
    else Left "Trend queries currently support only the month time grain."

validateObjectQueryTimeGrain :: Maybe TimeGrain -> Either Text ()
validateObjectQueryTimeGrain maybeTimeGrain =
  case maybeTimeGrain of
    Nothing -> pure ()
    Just _ -> Left "Object queries currently do not support time-grain trends."

validateTrendLimit :: Maybe Int -> Either Text ()
validateTrendLimit maybeLimit =
  case maybeLimit of
    Nothing -> pure ()
    Just _ -> Left "Trend queries currently do not support limit."

validateTrendLinkedFilters :: [LinkedFilter] -> Either Text ()
validateTrendLinkedFilters linkedFilterValues =
  if null linkedFilterValues
    then pure ()
    else Left "Trend queries currently do not support linked filters."

validateTrendFactSurface :: Object -> Either Text ()
validateTrendFactSurface factObject =
  if objectName factObject == "TeamGame"
    then pure ()
    else Left "Trend queries currently support TeamGame only."

validateSeasonFilters :: [Filter] -> Either Text ()
validateSeasonFilters filterValues =
  case seasonFilterPair filterValues of
    Just _ -> pure ()
    Nothing -> Left "Season queries currently require both an exact season label and an explicit season type."

seasonFilterPair :: [Filter] -> Maybe (Text, Text)
seasonFilterPair filterValues = do
  seasonLabel <- foldr pickExactSeasonValue Nothing filterValues
  seasonTypeLabel <- foldr pickSeasonTypeValue Nothing filterValues
  pure (seasonLabel, seasonTypeLabel)
  where
    pickExactSeasonValue filterValue currentValue =
      if filterKindText filterValue == "exact_season"
        then filterTextValue filterValue <|> currentValue
        else currentValue
    pickSeasonTypeValue filterValue currentValue =
      if filterKindText filterValue == "season_type"
        then filterTextValue filterValue <|> currentValue
        else currentValue

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
    ["team_name"] -> do
      rowObject <- requireReachableDimensionObject ontology (objectName factObject) "team_name"
      requireOrdinaryMetricDimensionOnObject rowObject "team_name"
      pure ()
    [_] -> Left "Trend queries currently support only aggregate output or team_name grouping."
    _ -> Left "Trend queries currently support at most one business grouping dimension."

validateComparisonQuery :: Ontology -> Object -> Object -> BaseQuery -> [PlayerRef] -> Either Text ()
validateComparisonQuery ontology factObject rowObject base playerRefs = do
  validateComparisonQueryShape base
  validateComparisonPath ontology factObject rowObject
  validateComparisonMetric (metrics base)
  validateComparisonEntities playerRefs

validateComparisonQueryShape :: BaseQuery -> Either Text ()
validateComparisonQueryShape base = do
  if null (linkedFilters base)
    then pure ()
    else Left "Comparison queries currently do not support linked filters."
  if null (orders base)
    then pure ()
    else Left "Comparison queries should not request ranking order."
  case timeGrain base of
    Nothing -> pure ()
    Just _ -> Left "Comparison queries currently do not support time-grain trends."
  case filters base of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue
      , gamesValue > 0 -> pure ()
    _ -> Left "Comparison queries currently require a positive LastNGames filter."
  case dimensions base of
    ["player_name"] -> pure ()
    _ -> Left "Comparison queries currently require the player_name dimension."

validateComparisonPath :: Ontology -> Object -> Object -> Either Text ()
validateComparisonPath ontology factObject rowObject = do
  _ <- requirePath ontology (objectName factObject) (objectName rowObject)
  -- Temporary slice restriction. Comparison is still hard-capped to one
  -- planner path even though entity references are now generalized players.
  -- TODO(core-4-first): Comparison is intentionally deferred behind the current
  -- v1 families: ranking/top-N, trend, aggregation, and filtering/joining.
  -- Broaden this only after those four single-step paths feel complete.
  if objectName factObject /= "PlayerGame" || objectName rowObject /= "Player"
    then Left "Comparison currently supports the PlayerGame -> Player path only."
    else pure ()

-- Temporary slice restriction. This should broaden once comparison planning
-- can reason over governed metrics more generally.
-- TODO(core-4-first): Leave comparison metric broadening for later. It is not
-- on the critical path for the current four target families.
validateComparisonMetric :: [MetricName] -> Either Text ()
validateComparisonMetric metricValues =
  if metricValues /= ["total_points"]
    then Left "Comparison currently supports total_points only."
    else pure ()

-- TODO(core-4-first): Keep comparison entity-count broadening out of scope
-- until the core single-step ranking/trend/aggregation/filter+join families are
-- complete and stable.
validateComparisonEntities :: [PlayerRef] -> Either Text ()
validateComparisonEntities playerRefs =
  if length playerRefs /= 2 || length (nub (map personId playerRefs)) /= 2
    then Left "Comparison requires exactly two distinct supported entities."
    else pure ()

validateLinkedFilters :: Ontology -> Text -> [LinkedFilter] -> Either Text ()
validateLinkedFilters ontology factObjectName linkedFilterValues =
  case linkedFilterValues of
    [] -> pure ()
    [linkedFilterValue] -> do
      if targetObject linkedFilterValue /= "Team"
        then Left "Linked filters currently support Team only."
        else pure ()
      _ <- requirePath ontology factObjectName "Team"
      targetObjectValue <- requireObject ontology "Team"
      requirePublicLinkedFilterDimension targetObjectValue (attribute linkedFilterValue)
    _ -> Left "Query currently supports at most one linked filter."

validateOrdinaryLinkedFilters :: Ontology -> OrdinaryLinkedFilterQueryKind -> OrdinaryMetricFilterFamily -> Text -> [LinkedFilter] -> Either Text ()
validateOrdinaryLinkedFilters ontology queryKind filterFamily factObjectName linkedFilterValues = do
  validateLinkedFilters ontology factObjectName linkedFilterValues
  case linkedFilterValues of
    [] -> pure ()
    _ -> validateLinkedFilterFactSurface ontology queryKind filterFamily factObjectName

validateLinkedFilterFactSurface :: Ontology -> OrdinaryLinkedFilterQueryKind -> OrdinaryMetricFilterFamily -> Text -> Either Text ()
validateLinkedFilterFactSurface ontology queryKind filterFamily factObjectName = do
  factObject <- requireObject ontology factObjectName
  case filterFamily of
    RecentMetricWindow -> requireFactAttribute factObject "game_date" (recentLinkedFilterFactSurfaceMessage queryKind)
    SeasonMetricWindow -> do
      requireFactAttribute factObject "season_year" (seasonLinkedFilterFactSurfaceMessage queryKind)
      requireFactAttribute factObject "season_type" (seasonLinkedFilterFactSurfaceMessage queryKind)
      validateSeasonLinkedFilterFactSurface queryKind factObject

recentLinkedFilterFactSurfaceMessage :: OrdinaryLinkedFilterQueryKind -> Text
recentLinkedFilterFactSurfaceMessage queryKind =
  case queryKind of
    MetricLinkedFilterQuery ->
      "Recent metric queries with linked filters currently require a fact surface that exposes game_date."
    ObjectLinkedFilterQuery ->
      "Recent object queries with linked filters currently require a fact surface that exposes game_date."

seasonLinkedFilterFactSurfaceMessage :: OrdinaryLinkedFilterQueryKind -> Text
seasonLinkedFilterFactSurfaceMessage queryKind =
  case queryKind of
    MetricLinkedFilterQuery ->
      "Season-scoped metric queries with linked filters currently require a fact surface that exposes season_year and season_type."
    ObjectLinkedFilterQuery ->
      "Season-scoped object queries with linked filters currently require a fact surface that exposes season_year and season_type."

requireFactAttribute :: Object -> Text -> Text -> Either Text ()
requireFactAttribute factObject attributeName failureMessage =
  case findAttribute factObject attributeName of
    Just _ -> pure ()
    _ -> Left failureMessage

validateSeasonLinkedFilterFactSurface :: OrdinaryLinkedFilterQueryKind -> Object -> Either Text ()
validateSeasonLinkedFilterFactSurface queryKind factObject =
  case queryKind of
    MetricLinkedFilterQuery ->
      if hasAttribute factObject "game_date"
        then Left "Season-scoped metric queries with linked filters currently require a season-level fact surface rather than per-game rows."
        else pure ()
    ObjectLinkedFilterQuery -> pure ()

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
  if OT.kind attribute == expectedKind
    then pure ()
    else Left ("Attribute '" <> attributeName <> "' has the wrong kind in the ontology.")

requirePublicLinkedFilterDimension :: Object -> Text -> Either Text ()
requirePublicLinkedFilterDimension object attributeName = do
  attribute <-
    maybe
      (Left ("Linked filters currently support public Team dimensions only."))
      Right
      (findAttribute object attributeName)
  if OT.kind attribute /= Dimension || OT.visibility attribute /= OT.Public
    then Left "Linked filters currently support public Team dimensions only."
    else pure ()

objectName :: OT.Object -> Text
objectName objectValue =
  case objectValue of
    OT.Object {OT.name = currentName} -> currentName

isPastYearFilter :: Filter -> Bool
isPastYearFilter filterValue =
  filterKindText filterValue == "past_year" && filterValueRef filterValue == Nothing
