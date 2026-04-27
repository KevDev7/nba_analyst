-- Purpose:
-- Shared grounded-planning validation helpers used across query families.
--
-- Uses:
-- - typed ontology values
-- - Query IR from the query-model step
--
-- Produces:
-- - family-agnostic validation building blocks

{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common where

import Control.Applicative ((<|>))
import Data.List (nub)
import Data.Text (Text)
import OntologyLayer.Graph (DiscoveredPath, findAttribute, findMetric, findObject, findPath, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (AttributeKind (Dimension), MetricDef (aggregation, executable, name, source_attributes), Object, Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

data OrdinaryMetricFilterFamily
  = RecentMetricWindow
  | SeasonMetricWindow

data OrdinaryLinkedFilterQueryKind
  = MetricLinkedFilterQuery
  | ObjectLinkedFilterQuery

validateTrendMetricQuery :: Ontology -> Object -> OT.MetricDef -> TimeGrain -> BaseQuery -> Either Text ()
validateTrendMetricQuery ontology factObject _metricDef timeGrainValue base = do
  validateTrendTimeGrain timeGrainValue
  validateTrendFilters factObject (filters base)
  validateTrendLimit (limit base)
  validateLinkedFilters ontology (objectName factObject) (linkedFilters base)
  validateTrendOrders (orders base)
  validateTrendFactSurface factObject timeGrainValue
  validateTrendDimensions ontology factObject (dimensions base)

requireOrdinaryMetricRowObject :: Ontology -> Object -> [DimensionName] -> Either Text Object
requireOrdinaryMetricRowObject ontology factObject dimensionValues = do
  dimensionName <- requireOrdinaryMetricDimension dimensionValues
  rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionName
  requireOrdinaryMetricDimensionOnObject rowObject dimensionName
  pure rowObject

requireComparisonRowObject :: Ontology -> Object -> [DimensionName] -> ComparisonIntent -> Either Text Object
requireComparisonRowObject ontology factObject dimensionValues comparisonIntent = do
  dimensionName <- requireComparisonDimension dimensionValues
  rowObject <- requireComparisonTargetObject ontology factObject comparisonIntent
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
    "Ranking/aggregation metric queries require exactly one selected metric."
    factObject
    metricValues

requireTrendSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireTrendSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Trend queries require exactly one selected metric."
    factObject
    metricValues

requireObjectQuerySelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireObjectQuerySelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Object queries require exactly one selected metric."
    factObject
    metricValues

requireComparisonSelectedMetric :: Object -> [MetricName] -> Either Text OT.MetricDef
requireComparisonSelectedMetric factObject metricValues =
  requireFamilySelectedMetric
    "Comparison queries require exactly one selected metric."
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
    _ -> Left "Ranking/aggregation metric queries require exactly one business grouping dimension."

requireObjectQueryDimensionName :: [DimensionName] -> Either Text DimensionName
requireObjectQueryDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Object queries require exactly one row dimension."

requireComparisonDimension :: [DimensionName] -> Either Text DimensionName
requireComparisonDimension dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Comparison queries require exactly one business grouping dimension."

requireOrdinaryMetricDimensionOnObject :: Object -> DimensionName -> Either Text ()
requireOrdinaryMetricDimensionOnObject object dimensionName = do
  let attributeName = dimensionName
  requireAttributeKind object attributeName Dimension

requireObjectQueryDimension :: Object -> [DimensionName] -> Either Text ()
requireObjectQueryDimension object dimensionValues = do
  dimensionName <- requireObjectQueryDimensionName dimensionValues
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
        else Left "Metric queries require either a positive LastNGames filter or an exact season plus season type filter bundle."

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

validateTrendFilters :: Object -> [Filter] -> Either Text ()
validateTrendFilters factObject filterValues = do
  if length filterKinds == length (nub filterKinds)
    then pure ()
    else Left "Trend queries do not support duplicate filter kinds."
  mapM_ validateTrendFilter filterValues
  where
    filterKinds = map filterKindText filterValues
    validateTrendFilter filterValue =
      case filterKindText filterValue of
        "past_year" -> do
          requireFactAttribute factObject "game_date" "Past-year trend filters require an ontology-backed game_date attribute."
          pure ()
        "season_type" ->
          case filterTextValue filterValue of
            Just _ -> do
              requireFactAttribute factObject "season_type" "Season-type trend filters require an ontology-backed season_type attribute."
              pure ()
            Nothing -> Left "Season-type trend filters require a text value."
        _ -> Left ("Unsupported trend filter kind '" <> filterKindText filterValue <> "'.")

validateTrendTimeGrain :: TimeGrain -> Either Text ()
validateTrendTimeGrain timeGrainValue =
  if timeGrainText timeGrainValue `elem` ["day", "week", timeGrainText monthTimeGrain, "season"]
    then pure ()
    else Left "Trend queries support calendar day, week, month, or season grains."

validateObjectQueryTimeGrain :: Maybe TimeGrain -> Either Text ()
validateObjectQueryTimeGrain maybeTimeGrain =
  case maybeTimeGrain of
    Nothing -> pure ()
    Just _ -> Left "Object queries do not support time-grain trends."

validateTrendLimit :: Maybe Int -> Either Text ()
validateTrendLimit maybeLimit =
  case maybeLimit of
    Nothing -> pure ()
    Just _ -> Left "Trend queries do not support limit."

validateTrendFactSurface :: Object -> TimeGrain -> Either Text ()
validateTrendFactSurface factObject timeGrainValue =
  case timeGrainText timeGrainValue of
    "day" -> requireFactAttribute factObject "game_date" trendFactSurfaceMessage
    "week" -> requireFactAttribute factObject "game_date" trendFactSurfaceMessage
    "month" -> requireFactAttribute factObject "game_date" trendFactSurfaceMessage
    "season" -> requireFactAttribute factObject "season_year" "Season trend queries require an ontology-backed season_year attribute."
    _ -> Left "Trend queries support calendar day, week, month, or season grains."

validateSeasonFilters :: [Filter] -> Either Text ()
validateSeasonFilters filterValues =
  case seasonFilterPair filterValues of
    Just _ -> pure ()
    Nothing -> Left "Season queries require both an exact season label and an explicit season type."

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
        ([orderValue], [selectedMetric]) | orderMetricName orderValue == selectedMetric -> pure ()
        _ -> Left "Ranking queries require ordering by the selected metric."

orderMetricName :: Order -> MetricName
orderMetricName orderValue =
  case orderValue of
    Asc metricNameValue -> metricNameValue
    Desc metricNameValue -> metricNameValue

validateOptionalMetricOrder :: [Order] -> [MetricName] -> Either Text ()
validateOptionalMetricOrder orderValues metricValues =
  case orderValues of
    [] -> pure ()
    [Desc orderMetric] ->
      case metricValues of
        [selectedMetric] | orderMetric == selectedMetric -> pure ()
        _ -> Left "Object queries require descending ordering on the selected metric when order is present."
    [Asc orderMetric] ->
      case metricValues of
        [selectedMetric] | orderMetric == selectedMetric -> pure ()
        _ -> Left "Object queries require ordering on the selected metric when order is present."
    _ -> Left "Object queries support at most one order on the selected metric."

validateTrendOrders :: [Order] -> Either Text ()
validateTrendOrders orderValues =
  if null orderValues
    then pure ()
    else Left "Trend queries do not accept explicit ordering."

validateTrendDimensions :: Ontology -> Object -> [DimensionName] -> Either Text ()
validateTrendDimensions ontology factObject dimensionValues =
  case dimensionValues of
    [] -> pure ()
    [dimensionValue] -> do
      rowObject <- requireReachableDimensionObject ontology (objectName factObject) dimensionValue
      requirePublicTrendDimensionOnObject rowObject dimensionValue
      pure ()
    _ -> Left "Trend queries support at most one business grouping dimension."

validateComparisonQuery :: Ontology -> Object -> Object -> OT.MetricDef -> BaseQuery -> ComparisonIntent -> [EntityRef] -> Either Text ()
validateComparisonQuery ontology factObject rowObject metricDef base comparisonIntent entityRefs = do
  validateComparisonQueryShape base
  validateLinkedFilters ontology (objectName factObject) (linkedFilters base)
  validateComparisonPath ontology factObject rowObject comparisonIntent
  validateComparisonMetric metricDef
  validateComparisonEntities entityRefs

validateComparisonQueryShape :: BaseQuery -> Either Text ()
validateComparisonQueryShape base = do
  if null (orders base)
    then pure ()
    else Left "Comparison queries should not request ranking order."
  case limit base of
    Nothing -> pure ()
    Just _ -> Left "Comparison queries do not support limit."
  case timeGrain base of
    Nothing -> pure ()
    Just _ -> Left "Comparison queries do not support time-grain trends."
  case filters base of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue
      , gamesValue > 0 -> pure ()
    _ -> Left "Comparison queries require a positive LastNGames filter."
  case dimensions base of
    [_] -> pure ()
    _ -> Left "Comparison queries require exactly one comparison identity dimension."

validateComparisonPath :: Ontology -> Object -> Object -> ComparisonIntent -> Either Text ()
validateComparisonPath ontology factObject rowObject comparisonIntent = do
  _ <- requireComparisonTargetPath ontology factObject rowObject comparisonIntent
  pure ()

validateComparisonMetric :: OT.MetricDef -> Either Text ()
validateComparisonMetric metricDef =
  if comparisonRuntimeMetricSupported metricDef
    then pure ()
    else Left "Comparison supports executable sum/avg metrics over recent row-level values only."

validateComparisonEntities :: [EntityRef] -> Either Text ()
validateComparisonEntities entityRefs =
  if length entityRefs < 2 || length (nub (map entityId entityRefs)) /= length entityRefs
    then Left "Comparison requires at least two distinct supported entities."
    else pure ()

validateLinkedFilters :: Ontology -> Text -> [LinkedFilter] -> Either Text ()
validateLinkedFilters ontology factObjectName linkedFilterValues =
  mapM_ validateLinkedFilter linkedFilterValues
  where
    validateLinkedFilter linkedFilterValue = do
      _ <- requirePath ontology factObjectName (targetObject linkedFilterValue)
      targetObjectValue <- requireObject ontology (targetObject linkedFilterValue)
      requirePublicLinkedFilterDimension targetObjectValue (attribute linkedFilterValue)

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
      "Recent metric queries with linked filters require a fact surface that exposes game_date."
    ObjectLinkedFilterQuery ->
      "Recent object queries with linked filters require a fact surface that exposes game_date."

seasonLinkedFilterFactSurfaceMessage :: OrdinaryLinkedFilterQueryKind -> Text
seasonLinkedFilterFactSurfaceMessage queryKind =
  case queryKind of
    MetricLinkedFilterQuery ->
      "Season-scoped metric queries with linked filters require a fact surface that exposes season_year and season_type."
    ObjectLinkedFilterQuery ->
      "Season-scoped object queries with linked filters require a fact surface that exposes season_year and season_type."

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
        then Left "Season-scoped metric queries with linked filters require a season-level fact surface rather than per-game rows."
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
      (Left ("Linked filters support public dimension attributes on reachable ontology objects only."))
      Right
      (findAttribute object attributeName)
  if OT.kind attribute /= Dimension || OT.visibility attribute /= OT.Public
    then Left "Linked filters support public dimension attributes on reachable ontology objects only."
    else pure ()

requirePublicTrendDimensionOnObject :: Object -> Text -> Either Text ()
requirePublicTrendDimensionOnObject object attributeName = do
  attribute <-
    maybe
      (Left ("Attribute '" <> attributeName <> "' not found in ontology."))
      Right
      (findAttribute object attributeName)
  if OT.kind attribute /= Dimension || OT.visibility attribute /= OT.Public
    then Left "Trend grouping supports reachable public dimension attributes only."
    else pure ()

requireComparisonDimensionOnObject :: Object -> DimensionName -> Either Text ()
requireComparisonDimensionOnObject object dimensionName = do
  attribute <-
    maybe
      (Left ("Attribute '" <> dimensionName <> "' not found in ontology."))
      Right
      (findAttribute object dimensionName)
  if OT.kind attribute /= Dimension || OT.visibility attribute /= OT.Public
    then Left "Comparison queries support public comparison identity dimensions only."
    else
      if OT.comparison_identity attribute
        then pure ()
        else Left "Comparison queries require a comparison identity dimension on the target object."

requireComparisonTargetObject :: Ontology -> Object -> ComparisonIntent -> Either Text Object
requireComparisonTargetObject ontology factObject comparisonIntent =
  case comparisonIntent of
    CompareEntities targetObjectName _ -> do
      targetObject <- requireObject ontology targetObjectName
      _ <- requireComparisonTargetPath ontology factObject targetObject comparisonIntent
      pure targetObject

requireComparisonTargetPath :: Ontology -> Object -> Object -> ComparisonIntent -> Either Text DiscoveredPath
requireComparisonTargetPath ontology factObject rowObject comparisonIntent =
  case comparisonIntent of
    CompareEntities targetObjectName _ ->
      if targetObjectName /= objectName rowObject
        then Left "Comparison target object and resolved comparison row object must match."
        else
          if targetObjectName == objectName factObject
            then Right (OG.DiscoveredPath (objectName factObject) (objectName factObject) [])
            else requirePath ontology (objectName factObject) targetObjectName

comparisonRuntimeMetricSupported :: OT.MetricDef -> Bool
comparisonRuntimeMetricSupported metricDef =
  executable metricDef
    && aggregation metricDef `elem` ["sum", "avg"]
    && length (source_attributes metricDef) == 1

trendFactSurfaceMessage :: Text
trendFactSurfaceMessage =
  "Trend queries require a fact surface that exposes an ontology-backed game_date attribute."

requireDerivedTrendBucket :: Object -> Text -> Either Text ()
requireDerivedTrendBucket object attributeName = do
  attribute <-
    maybe
      (Left trendFactSurfaceMessage)
      Right
      (findAttribute object attributeName)
  if OT.kind attribute /= Dimension || OT.derivation attribute == Nothing
    then Left trendFactSurfaceMessage
    else pure ()

objectName :: OT.Object -> Text
objectName objectValue =
  case objectValue of
    OT.Object {OT.name = currentName} -> currentName

isPastYearFilter :: Filter -> Bool
isPastYearFilter filterValue =
  filterKindText filterValue == "past_year" && filterValueRef filterValue == Nothing
