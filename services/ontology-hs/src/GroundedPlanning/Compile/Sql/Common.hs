{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Common
  ( combineWhereClauses
  , compileMetricAggregation
  , escapeSqlLiteral
  , labelsForRowObject
  , limitClause
  , renderColumnRefWithContext
  , renderFactExpression
  , renderFilterLiteral
  , renderLinkedFilterConditions
  , renderLinkedFilterJoinClauses
  , renderLinkedFilterWhereClause
  , renderMaybeColumnRef
  , renderMaybePathJoinClauses
  , renderMetricValue
  , renderMetadataAggregateSelectLines
  , renderMetadataDirectSelectLines
  , renderMetadataFinalSelectLines
  , renderMetadataSourceSelectLines
  , renderPathJoinClauses
  , renderSeasonFilterConditions
  , renderTrendFilterConditions
  , seasonWhereClause
  , seasonWhereClauseForAlias
  , trendSeasonTypeFromFilters
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Resolve
import OntologyLayer.Graph (DiscoveredPath)
import qualified OntologyLayer.Graph as OG
import QueryModel.IR (Filter, FilterValue (FilterInt, FilterText), filterKindText, filterTextValue)

-- Turn the resolved metric aggregation into the SQL aggregation expression.
-- This is where a semantic aggregation like "sum" becomes concrete SQL like SUM(...).
compileMetricAggregation :: ResolvedMetricFormula -> Text
compileMetricAggregation formula =
  case aggregationKind formula of
    "sum" -> "SUM(metric_source)"
    "avg" -> "ROUND(AVG(metric_source), 1)"
    "identity" -> "MAX(metric_source)"
    _ -> error "Unsupported executable metric aggregation."

renderTrendFilterConditions :: Text -> [Filter] -> [Text]
renderTrendFilterConditions trendFactTableName filterValues =
  mapMaybeTrendFilterCondition filterValues
  where
    latestDateSubquery = "(SELECT MAX(game_date) FROM " <> trendFactTableName <> ")"
    mapMaybeTrendFilterCondition [] = []
    mapMaybeTrendFilterCondition (filterValue : remaining) =
      case filterKindText filterValue of
        "past_year" ->
          ("f.game_date >= " <> latestDateSubquery <> " - INTERVAL '1 year'") : mapMaybeTrendFilterCondition remaining
        "season_type" ->
          case filterTextValue filterValue of
            Just seasonTypeValue -> ("f.season_type = '" <> seasonTypeValue <> "'") : mapMaybeTrendFilterCondition remaining
            Nothing -> mapMaybeTrendFilterCondition remaining
        _ -> mapMaybeTrendFilterCondition remaining

trendSeasonTypeFromFilters :: [Filter] -> Maybe Text
trendSeasonTypeFromFilters filterValues =
  case filterValues of
    [] -> Nothing
    filterValue : remaining ->
      if filterKindText filterValue == "season_type"
        then filterTextValue filterValue
        else trendSeasonTypeFromFilters remaining

-- Render a metric column reference based on where it lives in the query shape.
renderMetricValue :: ColumnRef -> Text
renderMetricValue columnRef =
  case tableRole columnRef of
    "fact" -> "f." <> columnName columnRef
    "row" -> "r." <> columnName columnRef
    "series" -> "r." <> columnName columnRef
    "context" -> "c." <> columnName columnRef
    _ -> error "Unsupported metric column role."

renderMetadataSourceSelectLines :: Text -> Text -> Text -> [ResolvedDisplayMetadata] -> [Text]
renderMetadataSourceSelectLines factAlias rowAlias contextAlias metadataValues =
  [ "    " <> renderColumnRefWithContext factAlias rowAlias contextAlias sourceColumn
      <> " AS __" <> metadataKey metadataValue <> "_source,"
  | metadataValue <- metadataValues
  , metadataAggregation metadataValue /= "count_rows"
  , Just sourceColumn <- [metadataSource metadataValue]
  ]

renderMetadataDirectSelectLines :: Text -> Text -> Text -> [ResolvedDisplayMetadata] -> [Text]
renderMetadataDirectSelectLines factAlias rowAlias contextAlias metadataValues =
  [ "    " <> renderColumnRefWithContext factAlias rowAlias contextAlias sourceColumn
      <> " AS " <> metadataKey metadataValue <> ","
  | metadataValue <- metadataValues
  , Just sourceColumn <- [metadataSource metadataValue]
  ]

renderMetadataAggregateSelectLines :: [ResolvedDisplayMetadata] -> [Text]
renderMetadataAggregateSelectLines metadataValues =
  map renderMetadata metadataValues
  where
    renderMetadata metadataValue =
      case metadataAggregation metadataValue of
        "count_rows" -> "    COUNT(*) AS " <> metadataKey metadataValue <> ","
        "avg" -> "    ROUND(AVG(__" <> metadataKey metadataValue <> "_source), 1) AS " <> metadataKey metadataValue <> ","
        "identity" -> "    MAX(__" <> metadataKey metadataValue <> "_source) AS " <> metadataKey metadataValue <> ","
        "date_range" ->
          "    CAST(MIN(__" <> metadataKey metadataValue <> "_source) AS VARCHAR)"
            <> " || ' to ' || CAST(MAX(__" <> metadataKey metadataValue <> "_source) AS VARCHAR)"
            <> " AS " <> metadataKey metadataValue <> ","
        _ -> error "Unsupported display metadata aggregation."

renderMetadataFinalSelectLines :: [ResolvedDisplayMetadata] -> [Text]
renderMetadataFinalSelectLines metadataValues =
  [ "  " <> metadataKey metadataValue <> ","
  | metadataValue <- metadataValues
  ]

seasonWhereClause :: Text -> Text -> Text
seasonWhereClause seasonLabelValue seasonTypeValue =
  seasonWhereClauseForAlias "f" seasonLabelValue seasonTypeValue

seasonWhereClauseForAlias :: Text -> Text -> Text -> Text
seasonWhereClauseForAlias factAlias seasonLabelValue seasonTypeValue =
  factAlias <> ".season_year = '" <> escapeSqlLiteral seasonLabelValue <> "' AND "
    <> factAlias <> ".season_type = '" <> escapeSqlLiteral seasonTypeValue <> "'"

renderSeasonFilterConditions :: Text -> Maybe Text -> Maybe Text -> [Text]
renderSeasonFilterConditions factAlias maybeSeasonLabel maybeSeasonType =
  case (maybeSeasonLabel, maybeSeasonType) of
    (Just seasonLabelValue, Just seasonTypeValue) ->
      [seasonWhereClauseForAlias factAlias seasonLabelValue seasonTypeValue]
    _ -> []

combineWhereClauses :: [Text] -> Text
combineWhereClauses clauseValues =
  T.intercalate " AND " clauseValues

-- Render a column reference using the right table alias for its role.
-- Example: a fact column becomes f.column_name, a row column becomes r.column_name.
renderColumnRefWithContext :: Text -> Text -> Text -> ColumnRef -> Text
renderColumnRefWithContext factAlias rowAlias contextAlias columnRef =
  case tableRole columnRef of
    "fact" -> factAlias <> "." <> columnName columnRef
    "row" -> rowAlias <> "." <> columnName columnRef
    "series" -> rowAlias <> "." <> columnName columnRef
    "context" -> contextAlias <> "." <> columnName columnRef
    _ -> error "Unsupported column role."

renderMaybeColumnRef :: Text -> Text -> Text -> Maybe ColumnRef -> Text
renderMaybeColumnRef factAlias rowAlias contextAlias maybeColumnRef =
  case maybeColumnRef of
    Just columnRef -> renderColumnRefWithContext factAlias rowAlias contextAlias columnRef
    Nothing -> "NULL"

renderFactExpression :: Text -> Text -> Text
renderFactExpression factAlias expressionText =
  T.replace "{fact_alias}" factAlias expressionText

-- Turn a discovered ontology path into SQL JOIN clauses.
-- Plain English: if Resolve.hs said "to get from the fact object to the row object,
-- walk these links", this helper turns that path into actual JOIN lines.
renderPathJoinClauses :: Text -> Text -> Text -> Text -> DiscoveredPath -> [Text]
renderPathJoinClauses joinKeyword baseAlias finalAlias intermediatePrefix discoveredPath =
  case OG.steps discoveredPath of
    [] -> []
    discoveredSteps ->
      concatMap renderIndexedStep (zip [0 :: Int ..] discoveredSteps)
      where
        finalIndex = length discoveredSteps - 1

        aliasAt :: Int -> Text
        aliasAt indexValue =
          if indexValue == finalIndex
            then finalAlias
            else intermediatePrefix <> T.pack (show (indexValue + 1))

        sourceAliasAt :: Int -> Text
        sourceAliasAt indexValue =
          if indexValue == 0
            then baseAlias
            else aliasAt (indexValue - 1)

        renderIndexedStep :: (Int, OG.PathStep) -> [Text]
        renderIndexedStep (indexValue, discoveredStep) =
          let targetAlias = aliasAt indexValue
              sourceAlias = sourceAliasAt indexValue
           in
          [ "  " <> joinKeyword <> " " <> OG.stepTargetTableName discoveredStep <> " " <> targetAlias
          , "    ON " <> sourceAlias <> "." <> OG.sourceKey discoveredStep <> " = " <> targetAlias <> "." <> OG.targetKey discoveredStep
          ]

renderMaybePathJoinClauses :: Text -> Text -> Text -> Text -> Maybe DiscoveredPath -> [Text]
renderMaybePathJoinClauses joinKeyword baseAlias finalAlias intermediatePrefix maybeDiscoveredPath =
  case maybeDiscoveredPath of
    Just discoveredPath -> renderPathJoinClauses joinKeyword baseAlias finalAlias intermediatePrefix discoveredPath
    Nothing -> []

-- Add JOIN clauses needed for linked filters like "players on the Knicks".
renderLinkedFilterJoinClauses :: Text -> [ResolvedLinkedFilter] -> [Text]
renderLinkedFilterJoinClauses baseAlias linkedFilterValues =
  concatMap renderIndexedFilter (zip [1 :: Int ..] linkedFilterValues)
  where
    renderIndexedFilter :: (Int, ResolvedLinkedFilter) -> [Text]
    renderIndexedFilter (indexValue, linkedFilterValue) =
      renderPathJoinClauses
        "JOIN"
        baseAlias
        (linkedFilterAlias indexValue linkedFilterValue)
        ("lf" <> T.pack (show indexValue) <> "p")
        (filterPath linkedFilterValue)

-- Add the WHERE wrapper for linked-filter conditions when any exist.
renderLinkedFilterWhereClause :: Text -> [ResolvedLinkedFilter] -> [Text]
renderLinkedFilterWhereClause baseAlias linkedFilterValues =
  case renderLinkedFilterConditions baseAlias linkedFilterValues of
    [] -> []
    conditions -> ["  WHERE " <> combineWhereClauses conditions]

-- Render the individual linked-filter predicates.
renderLinkedFilterConditions :: Text -> [ResolvedLinkedFilter] -> [Text]
renderLinkedFilterConditions _baseAlias linkedFilterValues =
  map renderIndexedCondition (zip [1 :: Int ..] linkedFilterValues)
  where
    renderIndexedCondition :: (Int, ResolvedLinkedFilter) -> Text
    renderIndexedCondition (indexValue, linkedFilterValue) =
      linkedFilterAlias indexValue linkedFilterValue
        <> "."
        <> filterColumn linkedFilterValue
        <> " = '"
        <> escapeSqlLiteral (filterValue linkedFilterValue)
        <> "'"

linkedFilterAlias :: Int -> ResolvedLinkedFilter -> Text
linkedFilterAlias indexValue linkedFilterValue =
  if null (OG.steps (filterPath linkedFilterValue))
    then "f"
    else "lf" <> T.pack (show indexValue)

escapeSqlLiteral :: Text -> Text
escapeSqlLiteral = T.replace "'" "''"

renderFilterLiteral :: FilterValue -> Text
renderFilterLiteral filterValue =
  case filterValue of
    FilterInt intValue -> T.pack (show intValue)
    FilterText textValue -> "'" <> escapeSqlLiteral textValue <> "'"

-- Turn an optional limit into a SQL LIMIT clause.
limitClause :: Maybe Int -> [Text]
limitClause maybeLimit =
  case maybeLimit of
    Just limitValue -> ["LIMIT " <> T.pack (show limitValue)]
    Nothing -> []

-- User-facing labels that Python/UI can show for result rows.
-- This is presentation metadata that rides along with the execution plan.
labelsForRowObject :: Text -> (Text, Text, Text)
labelsForRowObject rowObjectNameValue =
  case rowObjectNameValue of
    "Game" -> ("Game", "Games", "")
    "Player" -> ("Player", "Players", "Team")
    "PlayerSeason" -> ("Player", "Players", "")
    "Team" -> ("Team", "Teams", "Abbrev")
    "TeamSeason" -> ("Team", "Teams", "Abbrev")
    _ -> ("Entity", "Entities", "Context")
