-- Purpose:
-- Resolve the validated Query into grounded table, link, and metric-formula details.
--
-- Uses:
-- - typed ontology values
-- - validated Query IR
--
-- Produces:
-- - a grounded query description ready for compilation
--
-- Next:
-- - Compile.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve where

import Data.Aeson (FromJSON, ToJSON (toJSON), object, (.=))
import Data.Text (Text)
import GHC.Generics (Generic)
import OntologyLayer.Graph (DiscoveredPath (steps), findAttribute, findMetric, findObject, findPath, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (Attribute (derivation, kind, source_column), AttributeDerivation (sql_expression), AttributeKind (PrimaryKey), MetricDef (aggregation, executable, expression, name, source_attributes), Object (backing_table), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

data ResolvedEntity = ResolvedEntity
  { entityPersonId :: Int
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
  , timeGrain :: Text
  , linkedFiltersResolved :: [ResolvedLinkedFilter]
  , resolvedAssumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedObjectQuery = ResolvedObjectQuery
  { rowTableName :: Text
  , factTableName :: Text
  , rowObjectName :: Text
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

data ResolvedQuery
  = ResolvedMetric ResolvedMetricQuery
  | ResolvedTrend ResolvedTrendQuery
  | ResolvedObject ResolvedObjectQuery
  deriving (Show, Eq, Generic)

instance ToJSON ResolvedQuery where
  toJSON (ResolvedMetric resolved) =
    object ["kind" .= ("metric_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedTrend resolved) =
    object ["kind" .= ("metric_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedObject resolved) =
    object ["kind" .= ("object_query" :: Text), "resolved" .= resolved]

resolveQuery :: Ontology -> Query -> Either Text ResolvedQuery
resolveQuery ontology query =
  case query of
    MetricQuery spec ->
      case queryTimeGrain spec of
        Just _ -> ResolvedTrend <$> resolveTrendQuery ontology spec
        Nothing -> ResolvedMetric <$> resolveMetricQuery ontology spec
    ObjectQuery spec -> ResolvedObject <$> resolveObjectQuery ontology spec

resolveMetricQuery :: Ontology -> MetricQuerySpec -> Either Text ResolvedMetricQuery
resolveMetricQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  (rowObject, discoveredRowPath) <- resolveMetricRowObject ontology (coreFactObject base) (dimensions base)
  selectedMetric <- requireSingleMetric (metrics base)
  metricDef <- requireMetric factObject (metricText selectedMetric)
  displayColumn <- metricDisplayColumn (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObject
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObject
  resolvedLinkedFilters <- mapM (resolveLinkedFilter ontology (coreFactObject base)) (linkedFilters base)
  let maybeSeasonPair = seasonFilterPair (filters base)
      gamesValue =
        case maybeSeasonPair of
          Just _ -> 0
          Nothing ->
            case requireLastNGames (filters base) of
              Right value -> value
              Left _ -> 0
  let limitValue = limit base
      entityValues = map resolveEntity (entityFilters metricQuery)
      comparisonRequestedFlag =
        case comparison metricQuery of
          Just _ -> True
          Nothing -> False
      formula = resolveMetricFormula metricDef
  pure
    ResolvedMetricQuery
      { factTableName = backing_table factObject
      , rowTableName = backing_table rowObject
      , rowObjectName = objectName rowObject
      , rowPath = discoveredRowPath
      , contextPath = selectedContextPath contextSelection
      , partitionKey = pathPartitionKey rowPrimaryKey discoveredRowPath
      , entityId = ColumnRef "row" rowPrimaryKey
      , displayName = ColumnRef "row" displayColumn
      , contextValue = selectedContextColumn contextSelection
      , gameDate = ColumnRef "fact" "game_date"
      , metricSource = ColumnRef "fact" metricSourceColumn
      , windowGames = gamesValue
      , seasonLabel = fst <$> maybeSeasonPair
      , seasonType = snd <$> maybeSeasonPair
      , queryLimit = limitValue
      , linkedFiltersResolved = resolvedLinkedFilters
      , comparisonEntities = entityValues
      , comparisonRequestedValue = comparisonRequestedFlag
      , resolvedAssumptions = assumptions base
      , metricFormula = formula
      , filterLocation = "fact_table"
      }

resolveTrendQuery :: Ontology -> MetricQuerySpec -> Either Text ResolvedTrendQuery
resolveTrendQuery ontology metricQuery = do
  let base =
        case metricQuery of
          MetricQuerySpec {sharedQuery = currentBase} -> currentBase
  factObject <- requireObject ontology (coreFactObject base)
  selectedMetric <- requireSingleMetric (metrics base)
  metricDef <- requireMetric factObject (metricText selectedMetric)
  derivedAttribute <- requireDerivedTimeAttribute factObject (timeBucketAttributeName base)
  resolvedSeries <- resolveTrendSeries ontology factObject (dimensions base)
  metricSourceColumn <- metricSourceAttribute metricDef
  resolvedLinkedFilters <- mapM (resolveLinkedFilter ontology (coreFactObject base)) (linkedFilters base)
  pure
    ResolvedTrendQuery
      { factTableName = backing_table factObject
      , seriesTableName = backing_table . fst <$> resolvedSeries
      , seriesObjectName = objectName . fst <$> resolvedSeries
      , seriesPath = snd <$> resolvedSeries
      , seriesName = fmap (\(seriesObject, _) -> ColumnRef "series" (trendSeriesColumn seriesObject (dimensions base))) resolvedSeries
      , timeBucketName = "time_bucket"
      , timeBucketExpression = renderDerivedExpression derivedAttribute
      , metricSource = ColumnRef "fact" metricSourceColumn
      , metricFormula = resolveMetricFormula metricDef
      , filterLocation = "fact_table"
      , timeFilterKind = "past_year"
      , timeGrain = "month"
      , linkedFiltersResolved = resolvedLinkedFilters
      , resolvedAssumptions = assumptions base
      }

resolveObjectQuery :: Ontology -> ObjectQuerySpec -> Either Text ResolvedObjectQuery
resolveObjectQuery ontology objectQuery = do
  let base =
        case objectQuery of
          ObjectQuerySpec {sharedQuery = currentBase} -> currentBase
      rowObjectNameValue =
        case objectQuery of
          ObjectQuerySpec {rowObject = currentRowObject} -> currentRowObject
  factObject <- requireObject ontology (coreFactObject base)
  rowObjectValue <- requireObject ontology rowObjectNameValue
  discoveredRowPath <- requirePath ontology (coreFactObject base) rowObjectNameValue
  metricDef <- requireMetric factObject "total_points"
  displayColumn <- metricDisplayColumn (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObjectValue
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObjectValue
  resolvedLinkedFilters <- mapM (resolveLinkedFilter ontology (coreFactObject base)) (linkedFilters base)
  let maybeSeasonPair = seasonFilterPair (filters base)
      gamesValue =
        case maybeSeasonPair of
          Just _ -> 0
          Nothing ->
            case requireLastNGames (filters base) of
              Right value -> value
              Left _ -> 0
  pure
    ResolvedObjectQuery
      { rowTableName = backing_table rowObjectValue
      , factTableName = backing_table factObject
      , rowObjectName = rowObjectNameValue
      , rowPath = discoveredRowPath
      , contextPath = selectedContextPath contextSelection
      , partitionKey = pathPartitionKey rowPrimaryKey discoveredRowPath
      , entityId = ColumnRef "row" rowPrimaryKey
      , displayName = ColumnRef "row" displayColumn
      , contextValue = selectedContextColumn contextSelection
      , gameDate = ColumnRef "fact" "game_date"
      , metricSource = ColumnRef "fact" metricSourceColumn
      , windowGames = gamesValue
      , seasonLabel = fst <$> maybeSeasonPair
      , seasonType = snd <$> maybeSeasonPair
      , queryLimit = limit base
      , linkedFiltersResolved = resolvedLinkedFilters
      , resolvedAssumptions = assumptions base
      , metricFormula = resolveMetricFormula metricDef
      , filterLocation = "fact_table"
      }

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

resolveEntity :: PlayerRef -> ResolvedEntity
resolveEntity playerRef =
  -- Temporary direct passthrough. Slice 13 resolves player names in the
  -- interpreter and passes structured player refs into Haskell.
  ResolvedEntity
    { entityPersonId = personId playerRef
    , entityName = playerName playerRef
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
      , filterValue = value linkedFilterValue
      }

resolveMetricRowObject :: Ontology -> Text -> [DimensionName] -> Either Text (OT.Object, DiscoveredPath)
resolveMetricRowObject ontology factObjectName dimensionValues = do
  dimensionName <- requireSingleDimension dimensionValues
  attributeName <- dimensionKey dimensionName
  case firstLinkedObjectWithAttribute ontology factObjectName attributeName [] of
    Just resolvedValue -> Right resolvedValue
    Nothing -> do
      factObject <- requireObject ontology factObjectName
      if hasAttribute factObject attributeName
        then Right (factObject, emptyPath factObjectName)
        else Left ("Could not resolve a reachable row object for dimension '" <> attributeName <> "'.")

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
    , kind attribute == PrimaryKey
    ]
    of
    primaryKeyColumn : _ -> Right primaryKeyColumn
    [] -> Left ("Object '" <> objectName objectValue <> "' does not expose a primary key in the ontology.")

metricText :: MetricName -> Text
metricText metricValue =
  case metricValue of
    TotalPoints -> "total_points"
    AveragePoints -> "average_points"
    GamesPlayed -> "games_played"
    PointsPer36 -> "points_per_36"
    Wins -> "wins"
    Losses -> "losses"
    WinPercentage -> "win_percentage"

metricDisplayColumn :: [DimensionName] -> Either Text Text
metricDisplayColumn dimensionValues = do
  dimensionName <- requireSingleDimension dimensionValues
  dimensionKey dimensionName

metricSourceAttribute :: MetricDef -> Either Text Text
metricSourceAttribute metricDef =
  case source_attributes metricDef of
    sourceAttribute : _ -> Right sourceAttribute
    [] -> Left "Selected metric must reference at least one source attribute."

requireSingleMetric :: [MetricName] -> Either Text MetricName
requireSingleMetric metricValues =
  case metricValues of
    [metricValue] -> Right metricValue
    _ -> Left "Query requires exactly one selected metric."

requireLastNGames :: [Filter] -> Either Text Int
requireLastNGames filterValues =
  case filterValues of
    [LastNGames n] -> Right n
    _ -> Left "Only a single LastNGames filter is supported."

seasonFilterPair :: [Filter] -> Maybe (Text, Text)
seasonFilterPair filterValues = do
  seasonLabelValue <- foldr exactSeasonFilter Nothing filterValues
  seasonTypeValue <- foldr seasonTypeFilter Nothing filterValues
  pure (seasonLabelValue, seasonTypeValue)
  where
    exactSeasonFilter filterValue currentValue =
      case filterValue of
        ExactSeason seasonLabelValue -> Just seasonLabelValue
        _ -> currentValue
    seasonTypeFilter filterValue currentValue =
      case filterValue of
        SeasonTypeFilter seasonTypeValue -> Just seasonTypeValue
        _ -> currentValue

requireSingleDimension :: [DimensionName] -> Either Text DimensionName
requireSingleDimension dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Query requires exactly one selected dimension."

requireDerivedTimeAttribute :: OT.Object -> Text -> Either Text OT.Attribute
requireDerivedTimeAttribute objectValue attributeName =
  case findAttribute objectValue attributeName of
    Just attributeValue ->
      case derivation attributeValue of
        Just _ -> Right attributeValue
        Nothing -> Left ("Attribute '" <> attributeName <> "' is not configured as a derived time attribute.")
    Nothing -> Left ("Could not resolve derived time attribute '" <> attributeName <> "' against the ontology.")

timeBucketAttributeName :: BaseQuery -> Text
timeBucketAttributeName _ = "game_year_month"

resolveTrendSeries :: Ontology -> OT.Object -> [DimensionName] -> Either Text (Maybe (OT.Object, DiscoveredPath))
resolveTrendSeries ontology factObject dimensionValues =
  case dimensionValues of
    [] -> Right Nothing
    [dimensionValue] -> do
      seriesObject <- resolveMetricRowObject ontology (objectName factObject) [dimensionValue]
      pure (Just seriesObject)
    _ -> Left "Trend queries currently support at most one business grouping dimension."

trendSeriesColumn :: OT.Object -> [DimensionName] -> Text
trendSeriesColumn _ dimensionValues =
  case dimensionValues of
    [dimensionValue] ->
      case dimensionKey dimensionValue of
        Right columnNameValue -> columnNameValue
        Left _ -> error "Unsupported trend series dimension."
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

queryTimeGrain :: MetricQuerySpec -> Maybe TimeGrain
queryTimeGrain spec =
  case spec of
    MetricQuerySpec {sharedQuery = BaseQuery {timeGrain = currentTimeGrain}} -> currentTimeGrain
