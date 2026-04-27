-- Purpose:
-- Shared grounded-planning resolution types and helpers used across query families.
--
-- Uses:
-- - typed ontology values
-- - validated Query IR
--
-- Produces:
-- - family-agnostic grounded pieces ready for compilation

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common where

import Control.Applicative ((<|>))
import Data.Aeson (FromJSON, ToJSON (toJSON), object, (.=))
import Data.Text (Text)
import qualified Data.Text as T
import GHC.Generics (Generic)
import OntologyLayer.Graph (DiscoveredPath (steps), findAttribute, findMetric, findObject, findPath, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (Attribute (derivation, source_column), AttributeDerivation (sql_expression), AttributeKind (PrimaryKey), MetricDef (aggregation, executable, expression, name, source_attributes), Object (backing_table), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

data ResolvedEntity = ResolvedEntity
  { entityIdValue :: Int
  , entityName :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ColumnRef = ColumnRef
  { tableRole :: Text
  , columnName :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedMetricFormula = ResolvedMetricFormula
  { metricKey :: Text
  , aggregationKind :: Text
  , sourceAttributes :: [Text]
  , expressionText :: Text
  , executableInSlice :: Bool
  , resultColumn :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedLinkedFilter = ResolvedLinkedFilter
  { targetObjectName :: Text
  , filterPath :: DiscoveredPath
  , filterColumn :: Text
  , filterValue :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedMetricQuery = ResolvedMetricQuery
  { factTableName :: Text
  , rowTableName :: Text
  , rowObjectName :: Text
  , metricResultShape :: Text
  , metricOrderDirection :: Text
  , rowPath :: DiscoveredPath
  , contextPath :: Maybe DiscoveredPath
  , partitionKey :: ColumnRef
  , entityId :: ColumnRef
  , displayName :: ColumnRef
  , contextValue :: Maybe ColumnRef
  , gameDate :: ColumnRef
  , metricSource :: ColumnRef
  , windowGames :: Int
  , seasonLabel :: Maybe Text
  , seasonType :: Maybe Text
  , queryLimit :: Maybe Int
  , linkedFiltersResolved :: [ResolvedLinkedFilter]
  , comparisonEntities :: [ResolvedEntity]
  , comparisonRequestedValue :: Bool
  , resolvedAssumptions :: [Text]
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedTrendQuery = ResolvedTrendQuery
  { factTableName :: Text
  , seriesTableName :: Maybe Text
  , seriesObjectName :: Maybe Text
  , seriesPath :: Maybe DiscoveredPath
  , seriesName :: Maybe ColumnRef
  , timeBucketName :: Text
  , timeBucketExpression :: Text
  , metricSource :: ColumnRef
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
  , timeFilterKind :: Text
  , trendFilters :: [Filter]
  , timeGrain :: Text
  , linkedFiltersResolved :: [ResolvedLinkedFilter]
  , resolvedAssumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedObjectQuery = ResolvedObjectQuery
  { rowTableName :: Text
  , factTableName :: Text
  , rowObjectName :: Text
  , objectOrderDirection :: Text
  , rowPath :: DiscoveredPath
  , contextPath :: Maybe DiscoveredPath
  , partitionKey :: ColumnRef
  , entityId :: ColumnRef
  , displayName :: ColumnRef
  , contextValue :: Maybe ColumnRef
  , gameDate :: ColumnRef
  , metricSource :: ColumnRef
  , windowGames :: Int
  , seasonLabel :: Maybe Text
  , seasonType :: Maybe Text
  , queryLimit :: Maybe Int
  , linkedFiltersResolved :: [ResolvedLinkedFilter]
  , resolvedAssumptions :: [Text]
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindDisplay = ResolvedFindDisplay
  { displayPath :: DiscoveredPath
  , displayColumn :: Text
  , displayLabel :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindPredicate = ResolvedFindPredicate
  { predicatePath :: DiscoveredPath
  , predicateColumn :: Text
  , predicateLabel :: Text
  , predicateOp :: Text
  , predicateValue :: FilterValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedFindQuery = ResolvedFindQuery
  { resolvedFindFactTableName :: Text
  , resolvedFindTargetTableName :: Text
  , resolvedFindTargetObjectName :: Text
  , resolvedFindTargetPath :: DiscoveredPath
  , resolvedFindDisplays :: [ResolvedFindDisplay]
  , resolvedFindPredicates :: [ResolvedFindPredicate]
  , resolvedFindFilters :: [Filter]
  , resolvedFindLimit :: Maybe Int
  , resolvedFindAssumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedQuery
  = ResolvedMetric ResolvedMetricQuery
  | ResolvedTrend ResolvedTrendQuery
  | ResolvedObject ResolvedObjectQuery
  | ResolvedFind ResolvedFindQuery
  deriving (Show, Eq, Generic)

instance ToJSON ResolvedQuery where
  toJSON (ResolvedMetric resolved) =
    object ["kind" .= ("metric_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedTrend resolved) =
    object ["kind" .= ("metric_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedObject resolved) =
    object ["kind" .= ("object_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedFind resolved) =
    object ["kind" .= ("find_query" :: Text), "resolved" .= resolved]

data ContextSelection = ContextSelection
  { selectedContextPath :: Maybe DiscoveredPath
  , selectedContextColumn :: Maybe ColumnRef
  }

resolveContextSelection :: Ontology -> Text -> OT.Object -> Either Text ContextSelection
resolveContextSelection ontology factObjectName rowObject
  -- Temporary heuristic. This context selection prefers the first convenient
  -- team_abbreviation surface rather than modeling context selection as a more
  -- general semantic decision.
  | hasAttribute rowObject "team_abbreviation" =
      Right
        ContextSelection
          { selectedContextPath = Nothing
          , selectedContextColumn = Just (ColumnRef "row" "team_abbreviation")
          }
  | otherwise =
      case firstLinkedObjectWithAttribute ontology factObjectName "team_abbreviation" [objectName rowObject] of
        Just (_contextObject, discoveredContextPath) ->
          Right
            ContextSelection
              { selectedContextPath = Just discoveredContextPath
              , selectedContextColumn = Just (ColumnRef "context" "team_abbreviation")
              }
        Nothing ->
          Right
            ContextSelection
              { selectedContextPath = Nothing
              , selectedContextColumn = Nothing
              }

resolveMetricFormula :: MetricDef -> ResolvedMetricFormula
resolveMetricFormula metricDef =
  ResolvedMetricFormula
    { metricKey = name metricDef
    , aggregationKind = aggregation metricDef
    , sourceAttributes = source_attributes metricDef
    , expressionText = expression metricDef
    , executableInSlice = executable metricDef
    , resultColumn = "metric_value"
    }

orderDirectionText :: [Order] -> Text
orderDirectionText orderValues =
  case orderValues of
    Asc _ : _ -> "ASC"
    Desc _ : _ -> "DESC"
    [] -> "DESC"

resolveEntity :: EntityRef -> ResolvedEntity
resolveEntity entityRefValue =
  ResolvedEntity
    { entityIdValue =
        case entityRefValue of
          EntityRef {entityId = currentEntityId} -> currentEntityId
    , entityName =
        case entityRefValue of
          EntityRef {entityName = currentEntityName} -> currentEntityName
    }

resolveLinkedFilter :: Ontology -> Text -> LinkedFilter -> Either Text ResolvedLinkedFilter
resolveLinkedFilter ontology factObjectName linkedFilterValue = do
  discoveredFilterPath <- requirePath ontology factObjectName (targetObject linkedFilterValue)
  targetObjectValue <- requireObject ontology (targetObject linkedFilterValue)
  _ <- maybe
    (Left ("Could not resolve linked filter attribute '" <> attribute linkedFilterValue <> "' against the ontology."))
    Right
    (findAttribute targetObjectValue (attribute linkedFilterValue))
  pure
    ResolvedLinkedFilter
      { targetObjectName = targetObject linkedFilterValue
      , filterPath = discoveredFilterPath
      , filterColumn = attribute linkedFilterValue
      , filterValue =
          case linkedFilterValue of
            LinkedFilter {value = filterTextValue'} -> filterTextValue'
      }

resolveOrdinaryMetricRowObject :: Ontology -> Text -> [DimensionName] -> Either Text (OT.Object, DiscoveredPath)
resolveOrdinaryMetricRowObject ontology factObjectName dimensionValues = do
  dimensionName <- requireOrdinaryMetricDimensionName dimensionValues
  let attributeName = dimensionName
  case firstLinkedObjectWithAttribute ontology factObjectName attributeName [] of
    Just resolvedValue -> Right resolvedValue
    Nothing -> do
      factObject <- requireObject ontology factObjectName
      if hasAttribute factObject attributeName
        then Right (factObject, emptyPath factObjectName)
        else Left ("Could not resolve a reachable row object for ranking/aggregation dimension '" <> attributeName <> "'.")

resolveComparisonRowObject :: Ontology -> Text -> [DimensionName] -> Maybe Text -> Either Text (OT.Object, DiscoveredPath)
resolveComparisonRowObject ontology factObjectName dimensionValues maybeTargetObjectName = do
  dimensionName <- requireComparisonDimensionName dimensionValues
  let attributeName = dimensionName
  case maybeTargetObjectName of
    Just targetObjectName -> do
      targetObject <- requireObject ontology targetObjectName
      discoveredPath <-
        if targetObjectName == factObjectName
          then Right (emptyPath factObjectName)
          else requirePath ontology factObjectName targetObjectName
      if hasAttribute targetObject attributeName
        then Right (targetObject, discoveredPath)
        else Left ("Could not resolve comparison identity dimension '" <> attributeName <> "' on target object '" <> targetObjectName <> "'.")
    Nothing ->
      case firstLinkedObjectWithAttribute ontology factObjectName attributeName [] of
        Just resolvedValue -> Right resolvedValue
        Nothing -> do
          factObject <- requireObject ontology factObjectName
          if hasAttribute factObject attributeName
            then Right (factObject, emptyPath factObjectName)
            else Left ("Could not resolve a reachable row object for comparison dimension '" <> attributeName <> "'.")

firstLinkedObjectWithAttribute :: Ontology -> Text -> Text -> [Text] -> Maybe (OT.Object, DiscoveredPath)
firstLinkedObjectWithAttribute ontology factObjectName attributeName excludedObjectNames =
  -- Temporary planner restriction. Like validation, this helper only searches
  -- depth-2 ontology paths for the current slices.
  case
    [ (objectValue, discoveredPath)
    | discoveredPath <- findPathsFrom ontology 2 factObjectName
    , let targetObjectNameValue = OG.targetObjectName discoveredPath
    , targetObjectNameValue `notElem` excludedObjectNames
    , Just objectValue <- [findObject ontology targetObjectNameValue]
    , hasAttribute objectValue attributeName
    ]
    of
    resolvedValue : _ -> Just resolvedValue
    [] -> Nothing

emptyPath :: Text -> DiscoveredPath
emptyPath objectNameValue =
  OG.DiscoveredPath
    { OG.sourceObjectName = objectNameValue
    , OG.targetObjectName = objectNameValue
    , OG.steps = []
    }

pathPartitionKey :: Text -> DiscoveredPath -> ColumnRef
pathPartitionKey fallbackColumn discoveredPath =
  case steps discoveredPath of
    firstStep : _ -> ColumnRef "fact" (OG.sourceKey firstStep)
    [] -> ColumnRef "fact" fallbackColumn

hasAttribute :: OT.Object -> Text -> Bool
hasAttribute objectValue attributeName =
  case findAttribute objectValue attributeName of
    Just _ -> True
    Nothing -> False

objectPrimaryKey :: OT.Object -> Either Text Text
objectPrimaryKey objectValue =
  case
    [ source_column attribute
    | attribute <- OT.attributes objectValue
    , OT.kind attribute == PrimaryKey
    ]
    of
    primaryKeyColumn : _ -> Right primaryKeyColumn
    [] -> Left ("Object '" <> objectName objectValue <> "' does not expose a primary key in the ontology.")

metricDisplayColumn :: [DimensionName] -> Either Text Text
metricDisplayColumn dimensionValues = do
  dimensionName <- requireAnySingleDimensionName dimensionValues
  pure dimensionName

metricSourceAttribute :: MetricDef -> Either Text Text
metricSourceAttribute metricDef =
  case source_attributes metricDef of
    sourceAttribute : _ -> Right sourceAttribute
    [] -> Left "Selected metric must reference at least one source attribute."

requireOrdinaryMetricName :: [MetricName] -> Either Text MetricName
requireOrdinaryMetricName metricValues =
  requireExactlyOneMetricName
    "Ranking/aggregation metric queries require exactly one selected metric."
    metricValues

requireTrendMetricName :: [MetricName] -> Either Text MetricName
requireTrendMetricName metricValues =
  requireExactlyOneMetricName
    "Trend queries require exactly one selected metric."
    metricValues

requireObjectQueryMetricName :: [MetricName] -> Either Text MetricName
requireObjectQueryMetricName metricValues =
  requireExactlyOneMetricName
    "Object queries require exactly one selected metric."
    metricValues

requireComparisonMetricName :: [MetricName] -> Either Text MetricName
requireComparisonMetricName metricValues =
  requireExactlyOneMetricName
    "Comparison queries require exactly one selected metric."
    metricValues

requireExactlyOneMetricName :: Text -> [MetricName] -> Either Text MetricName
requireExactlyOneMetricName cardinalityMessage metricValues =
  case metricValues of
    [metricValue] -> Right metricValue
    _ -> Left cardinalityMessage

requireLastNGames :: [Filter] -> Either Text Int
requireLastNGames filterValues =
  case filterValues of
    [filterValue]
      | filterKindText filterValue == "last_n_games"
      , Just gamesValue <- filterIntValue filterValue -> Right gamesValue
    _ -> Left "Only a single LastNGames filter is supported."

seasonFilterPair :: [Filter] -> Maybe (Text, Text)
seasonFilterPair filterValues = do
  seasonLabelValue <- foldr pickExactSeasonValue Nothing filterValues
  seasonTypeValue <- foldr pickSeasonTypeValue Nothing filterValues
  pure (seasonLabelValue, seasonTypeValue)
  where
    pickExactSeasonValue filterValue currentValue =
      if filterKindText filterValue == "exact_season"
        then filterTextValue filterValue <|> currentValue
        else currentValue
    pickSeasonTypeValue filterValue currentValue =
      if filterKindText filterValue == "season_type"
        then filterTextValue filterValue <|> currentValue
        else currentValue

requireAnySingleDimensionName :: [DimensionName] -> Either Text DimensionName
requireAnySingleDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Current runtime result shapes require exactly one selected dimension."

requireOrdinaryMetricDimensionName :: [DimensionName] -> Either Text DimensionName
requireOrdinaryMetricDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Ranking/aggregation metric queries require exactly one business grouping dimension."

requireComparisonDimensionName :: [DimensionName] -> Either Text DimensionName
requireComparisonDimensionName dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Comparison queries require exactly one business grouping dimension."

requireDerivedTimeAttribute :: OT.Object -> Text -> Either Text OT.Attribute
requireDerivedTimeAttribute objectValue attributeName =
  case findAttribute objectValue attributeName of
    Just attributeValue ->
      case derivation attributeValue of
        Just _ -> Right attributeValue
        Nothing -> Left ("Attribute '" <> attributeName <> "' is not configured as a derived time attribute.")
    Nothing -> Left ("Could not resolve derived time attribute '" <> attributeName <> "' against the ontology.")

timeBucketAttributeName :: TimeGrain -> Text
timeBucketAttributeName timeGrainValue =
  case timeGrainText timeGrainValue of
    "day" -> "game_date"
    "week" -> "game_date"
    "month" -> "game_year_month"
    "season" -> "season_year"
    _ -> error "Expected a supported trend time grain."

timeBucketExpressionFor :: TimeGrain -> Text
timeBucketExpressionFor timeGrainValue =
  -- Build the SQL bucket from an ontology-backed date/season attribute.
  -- Day/week/month use game_date; season uses season_year.
  case timeGrainText timeGrainValue of
    "day" -> "STRFTIME({fact_alias}.game_date, '%Y-%m-%d')"
    "week" -> "STRFTIME(DATE_TRUNC('week', {fact_alias}.game_date), '%Y-%m-%d')"
    "month" -> "STRFTIME({fact_alias}.game_date, '%Y-%m')"
    "season" -> "{fact_alias}.season_year"
    _ -> error "Expected a supported trend time grain."

trendFilterKindText :: [Filter] -> Text
trendFilterKindText filterValues =
  case map filterKindText filterValues of
    [] -> "all"
    kindValues -> T.intercalate "+" kindValues

resolveTrendSeries :: Ontology -> OT.Object -> [DimensionName] -> Either Text (Maybe (OT.Object, DiscoveredPath))
resolveTrendSeries ontology factObject dimensionValues =
  case dimensionValues of
    [] -> Right Nothing
    [dimensionValue] -> do
      seriesObject <- resolveOrdinaryMetricRowObject ontology (objectName factObject) [dimensionValue]
      pure (Just seriesObject)
    _ -> Left "Trend queries support at most one business grouping dimension."

trendSeriesColumn :: OT.Object -> [DimensionName] -> Text
trendSeriesColumn _ dimensionValues =
  case dimensionValues of
    [dimensionValue] -> dimensionValue
    _ -> error "Trend series columns require exactly one business grouping dimension."

renderDerivedExpression :: OT.Attribute -> Text
renderDerivedExpression attributeValue =
  case derivation attributeValue of
    Just derivationValue -> sql_expression derivationValue
    Nothing -> error "Expected a derived attribute expression."

requireObject :: Ontology -> Text -> Either Text OT.Object
requireObject ontology objectNameValue =
  maybe (Left ("Could not resolve object '" <> objectNameValue <> "' against the ontology.")) Right $
    findObject ontology objectNameValue

requireMetric :: OT.Object -> Text -> Either Text MetricDef
requireMetric objectValue metricNameValue =
  maybe (Left ("Could not resolve metric '" <> metricNameValue <> "' against the ontology.")) Right $
    findMetric objectValue metricNameValue

requirePath :: Ontology -> Text -> Text -> Either Text DiscoveredPath
requirePath ontology sourceName targetName =
  maybe
    (Left ("Could not resolve an ontology path from '" <> sourceName <> "' to '" <> targetName <> "'."))
    Right
    (findPath ontology 2 sourceName targetName)

objectName :: OT.Object -> Text
objectName objectValue =
  case objectValue of
    OT.Object {OT.name = currentName} -> currentName

queryTimeGrain :: MetricQuerySpec -> Maybe TimeGrain
queryTimeGrain spec =
  case spec of
    MetricQuerySpec {sharedQuery = BaseQuery {timeGrain = currentTimeGrain}} -> currentTimeGrain

requireTrendTimeGrainValue :: Maybe TimeGrain -> Either Text TimeGrain
requireTrendTimeGrainValue maybeTimeGrain =
  case maybeTimeGrain of
    Just timeGrainValue -> Right timeGrainValue
    Nothing -> Left "Trend queries require a time grain."
