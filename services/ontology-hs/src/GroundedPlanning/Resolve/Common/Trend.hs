{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Resolve.Common.Trend
  ( queryTimeGrain
  , renderDerivedExpression
  , requireDerivedTimeAttribute
  , requireTrendTimeGrainValue
  , resolveTrendSeries
  , timeBucketAttributeName
  , timeBucketExpressionFor
  , trendFilterKindText
  , trendSeriesColumn
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Resolve.Common.Dimensions
import GroundedPlanning.Resolve.Common.Ontology
import OntologyLayer.Graph (DiscoveredPath)
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (Attribute (derivation), AttributeDerivation (sql_expression), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

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

queryTimeGrain :: MetricQuerySpec -> Maybe TimeGrain
queryTimeGrain spec =
  case spec of
    MetricQuerySpec {sharedQuery = BaseQuery {timeGrain = currentTimeGrain}} -> currentTimeGrain

requireTrendTimeGrainValue :: Maybe TimeGrain -> Either Text TimeGrain
requireTrendTimeGrainValue maybeTimeGrain =
  case maybeTimeGrain of
    Just timeGrainValue -> Right timeGrainValue
    Nothing -> Left "Trend queries require a time grain."
