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
import OntologyLayer.Types (Attribute (kind, source_column), AttributeKind (PrimaryKey), MetricDef (aggregation, executable, expression, name, source_attributes), Object (backing_table), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

data ResolvedEntity = ResolvedEntity
  { entityName :: EntityName
  , entityColumnValue :: Text
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
  , queryLimit :: Maybe Int
  , comparisonEntities :: [ResolvedEntity]
  , comparisonRequestedValue :: Bool
  , resolvedAssumptions :: [Text]
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
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
  , queryLimit :: Maybe Int
  , resolvedAssumptions :: [Text]
  , metricFormula :: ResolvedMetricFormula
  , filterLocation :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ResolvedQuery
  = ResolvedMetric ResolvedMetricQuery
  | ResolvedObject ResolvedObjectQuery
  deriving (Show, Eq, Generic)

instance ToJSON ResolvedQuery where
  toJSON (ResolvedMetric resolved) =
    object ["kind" .= ("metric_query" :: Text), "resolved" .= resolved]
  toJSON (ResolvedObject resolved) =
    object ["kind" .= ("object_query" :: Text), "resolved" .= resolved]

resolveQuery :: Ontology -> Query -> Either Text ResolvedQuery
resolveQuery ontology query =
  case query of
    MetricQuery spec -> ResolvedMetric <$> resolveMetricQuery ontology spec
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
  gamesValue <- requireLastNGames (filters base)
  displayColumn <- metricDisplayColumn (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObject
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObject
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
      , queryLimit = limitValue
      , comparisonEntities = entityValues
      , comparisonRequestedValue = comparisonRequestedFlag
      , resolvedAssumptions = assumptions base
      , metricFormula = formula
      , filterLocation = "fact_table"
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
  gamesValue <- requireLastNGames (filters base)
  displayColumn <- metricDisplayColumn (dimensions base)
  contextSelection <- resolveContextSelection ontology (coreFactObject base) rowObjectValue
  metricSourceColumn <- metricSourceAttribute metricDef
  rowPrimaryKey <- objectPrimaryKey rowObjectValue
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
      , queryLimit = limit base
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

resolveEntity :: EntityName -> ResolvedEntity
resolveEntity entityValue =
  case entityValue of
    Brunson -> ResolvedEntity Brunson "Jalen Brunson"
    Haliburton -> ResolvedEntity Haliburton "Tyrese Haliburton"

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

requireSingleDimension :: [DimensionName] -> Either Text DimensionName
requireSingleDimension dimensionValues =
  case dimensionValues of
    [dimensionValue] -> Right dimensionValue
    _ -> Left "Query requires exactly one selected dimension."

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
