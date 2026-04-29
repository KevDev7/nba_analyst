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
  , renderGameDateFilterConditions
  , renderDisplayMetricAggregateSelectLines
  , renderDisplayMetricDirectSelectLines
  , renderDisplayMetricFinalSelectLines
  , renderDisplayMetricSourceSelectLines
  , groupingAlias
  , primaryGroupingKey
  , renderMaybeColumnRef
  , renderMaybePathJoinClauses
  , renderMetricValue
  , renderMetadataAggregateSelectLines
  , renderMetadataDirectSelectLines
  , renderMetadataFinalSelectLines
  , renderMetadataSourceSelectLines
  , renderGroupingAggregateSelectLines
  , renderGroupingFinalSelectLines
  , renderGroupingJoinClauses
  , renderGroupingKeys
  , renderGroupingOrder
  , renderGroupingSource
  , renderGroupingSourceSelectLines
  , renderPathJoinClauses
  , renderResultPredicateAggregateSelectLines
  , renderResultPredicateConditions
  , renderResultPredicateDirectSelectLines
  , renderResultPredicateFinalSelectLines
  , renderResultPredicateSourceSelectLines
  , renderRowPredicateConditions
  , renderRowPredicateJoinClauses
  , renderSeasonFilterConditions
  , renderTrendFilterConditions
  , trendSeasonLabelFromFilters
  , seasonWhereClause
  , seasonWhereClauseForAlias
  , trendSeasonTypeFromFilters
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Resolve
import OntologyLayer.Graph (DiscoveredPath)
import qualified OntologyLayer.Graph as OG
import QueryModel.IR (Filter, FilterValue (FilterDouble, FilterInt, FilterText), PredicateOperator (..), PredicateValue (..), filterIntValue, filterKindText, filterTextValue)

data IndexedRowPredicateTree
  = IndexedRowPredicateLeaf Int ResolvedRowPredicateLeaf
  | IndexedRowPredicateAnd [IndexedRowPredicateTree]
  | IndexedRowPredicateOr [IndexedRowPredicateTree]
  | IndexedRowPredicateNot IndexedRowPredicateTree

data IndexedResultPredicateTree
  = IndexedResultPredicateLeaf ResolvedResultPredicateLeaf
  | IndexedResultPredicateAnd [IndexedResultPredicateTree]
  | IndexedResultPredicateOr [IndexedResultPredicateTree]
  | IndexedResultPredicateNot IndexedResultPredicateTree

-- Turn the resolved metric aggregation into the SQL aggregation expression.
-- This is where a semantic aggregation like "sum" becomes concrete SQL like SUM(...).
compileMetricAggregation :: ResolvedMetricFormula -> Text
compileMetricAggregation formula =
  case aggregationKind formula of
    "sum" -> "SUM(metric_source)"
    "avg" -> "ROUND(AVG(metric_source), 1)"
    "identity" -> "MAX(metric_source)"
    _ -> error "Unsupported executable metric aggregation."

compileResultPredicateAggregation :: ResolvedResultPredicateLeaf -> Text
compileResultPredicateAggregation predicateLeaf =
  case resultPredicateAggregation predicateLeaf of
    "sum" -> "SUM(__" <> resultPredicateKey predicateLeaf <> "_source)"
    "avg" -> "ROUND(AVG(__" <> resultPredicateKey predicateLeaf <> "_source), 1)"
    "identity" -> "MAX(__" <> resultPredicateKey predicateLeaf <> "_source)"
    _ -> error "Unsupported result-predicate aggregation."

renderTrendFilterConditions :: Text -> [Filter] -> [Text]
renderTrendFilterConditions trendFactTableName filterValues =
  renderGameDateFilterConditions trendFactTableName "f" filterValues

renderGameDateFilterConditions :: Text -> Text -> [Filter] -> [Text]
renderGameDateFilterConditions factTableNameValue factAlias filterValues =
  mapMaybeDateFilterCondition filterValues
  where
    latestDateSubquery = "(SELECT MAX(game_date) FROM " <> factTableNameValue <> ")"
    gameDateColumn = factAlias <> ".game_date"
    mapMaybeDateFilterCondition [] = []
    mapMaybeDateFilterCondition (filterValue : remaining) =
      case filterKindText filterValue of
        "past_year" ->
          (gameDateColumn <> " >= " <> latestDateSubquery <> " - INTERVAL '1 year'") : mapMaybeDateFilterCondition remaining
        "last_n_days" ->
          case filterIntValue filterValue of
            Just daysValue ->
              (gameDateColumn <> " >= " <> latestDateSubquery <> " - INTERVAL '" <> T.pack (show daysValue) <> " days'") : mapMaybeDateFilterCondition remaining
            Nothing -> mapMaybeDateFilterCondition remaining
        "date_from" ->
          case filterTextValue filterValue of
            Just startDate -> (gameDateColumn <> " >= DATE '" <> escapeSqlLiteral startDate <> "'") : mapMaybeDateFilterCondition remaining
            Nothing -> mapMaybeDateFilterCondition remaining
        "date_to" ->
          case filterTextValue filterValue of
            Just endDate -> (gameDateColumn <> " <= DATE '" <> escapeSqlLiteral endDate <> "'") : mapMaybeDateFilterCondition remaining
            Nothing -> mapMaybeDateFilterCondition remaining
        "season_type" ->
          case filterTextValue filterValue of
            Just seasonTypeValue -> (factAlias <> ".season_type = '" <> escapeSqlLiteral seasonTypeValue <> "'") : mapMaybeDateFilterCondition remaining
            Nothing -> mapMaybeDateFilterCondition remaining
        "exact_season" ->
          case filterTextValue filterValue of
            Just seasonLabelValue -> (factAlias <> ".season_year = '" <> escapeSqlLiteral seasonLabelValue <> "'") : mapMaybeDateFilterCondition remaining
            Nothing -> mapMaybeDateFilterCondition remaining
        _ -> mapMaybeDateFilterCondition remaining

trendSeasonLabelFromFilters :: [Filter] -> Maybe Text
trendSeasonLabelFromFilters filterValues =
  case filterValues of
    [] -> Nothing
    filterValue : remaining ->
      if filterKindText filterValue == "exact_season"
        then filterTextValue filterValue
        else trendSeasonLabelFromFilters remaining

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

compileDisplayMetricAggregation :: ResolvedMetricFormula -> Text
compileDisplayMetricAggregation formula =
  case aggregationKind formula of
    "sum" -> "SUM(__" <> resultColumn formula <> "_source)"
    "avg" -> "ROUND(AVG(__" <> resultColumn formula <> "_source), 1)"
    "identity" -> "MAX(__" <> resultColumn formula <> "_source)"
    _ -> error "Unsupported executable display-metric aggregation."

displayMetricSourceAttribute :: ResolvedMetricFormula -> Maybe Text
displayMetricSourceAttribute formula =
  case sourceAttributes formula of
    sourceAttribute : _ -> Just sourceAttribute
    [] -> Nothing

extraDisplayMetricFormulas :: [ResolvedMetricFormula] -> [ResolvedMetricFormula]
extraDisplayMetricFormulas metricFormulas =
  [ formula
  | formula <- metricFormulas
  , resultColumn formula /= "metric_value"
  ]

renderDisplayMetricSourceSelectLines :: Text -> [ResolvedMetricFormula] -> [Text]
renderDisplayMetricSourceSelectLines factAlias metricFormulas =
  [ "    " <> factAlias <> "." <> sourceAttribute <> " AS __" <> resultColumn formula <> "_source,"
  | formula <- extraDisplayMetricFormulas metricFormulas
  , Just sourceAttribute <- [displayMetricSourceAttribute formula]
  ]

renderDisplayMetricAggregateSelectLines :: [ResolvedMetricFormula] -> [Text]
renderDisplayMetricAggregateSelectLines metricFormulas =
  [ "    " <> compileDisplayMetricAggregation formula <> " AS " <> resultColumn formula <> ","
  | formula <- extraDisplayMetricFormulas metricFormulas
  ]

renderDisplayMetricDirectSelectLines :: Text -> [ResolvedMetricFormula] -> [Text]
renderDisplayMetricDirectSelectLines factAlias metricFormulas =
  [ "    " <> factAlias <> "." <> sourceAttribute <> " AS " <> resultColumn formula <> ","
  | formula <- extraDisplayMetricFormulas metricFormulas
  , Just sourceAttribute <- [displayMetricSourceAttribute formula]
  ]

renderDisplayMetricFinalSelectLines :: [ResolvedMetricFormula] -> [Text]
renderDisplayMetricFinalSelectLines metricFormulas =
  [ "  " <> resultColumn formula <> ","
  | formula <- extraDisplayMetricFormulas metricFormulas
  ]

renderResultPredicateSourceSelectLines :: Text -> Maybe ResolvedResultPredicateTree -> [Text]
renderResultPredicateSourceSelectLines factAlias maybePredicateTree =
  [ "    " <> factAlias <> "." <> sourceColumn <> " AS __" <> resultPredicateKey predicateLeaf <> "_source,"
  | predicateLeaf <- resultPredicateAuxiliaryLeaves maybePredicateTree
  , Just sourceColumn <- [resultPredicateColumn predicateLeaf]
  ]

renderResultPredicateAggregateSelectLines :: Maybe ResolvedResultPredicateTree -> [Text]
renderResultPredicateAggregateSelectLines maybePredicateTree =
  [ "    " <> compileResultPredicateAggregation predicateLeaf <> " AS " <> resultPredicateKey predicateLeaf <> ","
  | predicateLeaf <- resultPredicateAuxiliaryLeaves maybePredicateTree
  ]

renderResultPredicateDirectSelectLines :: Text -> Maybe ResolvedResultPredicateTree -> [Text]
renderResultPredicateDirectSelectLines factAlias maybePredicateTree =
  [ "    " <> factAlias <> "." <> sourceColumn <> " AS " <> resultPredicateKey predicateLeaf <> ","
  | predicateLeaf <- resultPredicateAuxiliaryLeaves maybePredicateTree
  , Just sourceColumn <- [resultPredicateColumn predicateLeaf]
  ]

renderResultPredicateFinalSelectLines :: Maybe ResolvedResultPredicateTree -> [Text]
renderResultPredicateFinalSelectLines maybePredicateTree =
  [ "  " <> resultPredicateKey predicateLeaf <> ","
  | predicateLeaf <- resultPredicateAuxiliaryLeaves maybePredicateTree
  ]

renderGroupingJoinClauses :: [ResolvedGroupingDimension] -> [Text]
renderGroupingJoinClauses groupingDimensions =
  concatMap renderGroupingJoin (zip [1 :: Int ..] groupingDimensions)
  where
    renderGroupingJoin (indexValue, groupingDimension) =
      if null (OG.steps (groupingPath groupingDimension))
        then []
        else
          renderPathJoinClauses
            "JOIN"
            "f"
            (groupingAlias indexValue)
            (groupingAlias indexValue <> "p")
            (groupingPath groupingDimension)

renderGroupingSourceSelectLines :: [ResolvedGroupingDimension] -> [Text]
renderGroupingSourceSelectLines groupingDimensions =
  [ "    " <> renderGroupingSource indexValue groupingDimension <> " AS " <> groupingKey groupingDimension <> ","
  | (indexValue, groupingDimension) <- zip [1 :: Int ..] groupingDimensions
  ]

renderGroupingSource :: Int -> ResolvedGroupingDimension -> Text
renderGroupingSource indexValue groupingDimension =
  case tableRole (groupingSource groupingDimension) of
    "fact" -> "f." <> columnName (groupingSource groupingDimension)
    "group" -> groupingAlias indexValue <> "." <> columnName (groupingSource groupingDimension)
    _ -> error "Unsupported grouping column role."

renderGroupingAggregateSelectLines :: [ResolvedGroupingDimension] -> [Text]
renderGroupingAggregateSelectLines groupingDimensions =
  [ "    " <> groupingKey groupingDimension <> ","
  | groupingDimension <- groupingDimensions
  ]

renderGroupingFinalSelectLines :: [ResolvedGroupingDimension] -> [Text]
renderGroupingFinalSelectLines groupingDimensions =
  [ "  " <> groupingKey groupingDimension <> ","
  | groupingDimension <- groupingDimensions
  ]

renderGroupingKeys :: [ResolvedGroupingDimension] -> Text
renderGroupingKeys groupingDimensions =
  T.intercalate ", " (map groupingKey groupingDimensions)

renderGroupingOrder :: [ResolvedGroupingDimension] -> Text
renderGroupingOrder groupingDimensions =
  T.intercalate ", " [groupingKey groupingDimension <> " ASC" | groupingDimension <- groupingDimensions]

primaryGroupingKey :: [ResolvedGroupingDimension] -> Text
primaryGroupingKey groupingDimensions =
  case groupingDimensions of
    groupingDimension : _ -> groupingKey groupingDimension
    [] -> "entity_name"

groupingAlias :: Int -> Text
groupingAlias indexValue =
  "g" <> T.pack (show indexValue)

renderResultPredicateConditions :: Maybe ResolvedResultPredicateTree -> [Text]
renderResultPredicateConditions maybePredicateTree =
  case maybePredicateTree of
    Nothing -> []
    Just predicateTree -> [renderResultPredicateTreeCondition (indexResultPredicateTree predicateTree)]

indexResultPredicateTree :: ResolvedResultPredicateTree -> IndexedResultPredicateTree
indexResultPredicateTree predicateTree =
  case predicateTree of
    ResolvedResultPredicateLeafNode predicateLeaf -> IndexedResultPredicateLeaf predicateLeaf
    ResolvedResultPredicateAnd predicateValues -> IndexedResultPredicateAnd (map indexResultPredicateTree predicateValues)
    ResolvedResultPredicateOr predicateValues -> IndexedResultPredicateOr (map indexResultPredicateTree predicateValues)
    ResolvedResultPredicateNot predicateValue -> IndexedResultPredicateNot (indexResultPredicateTree predicateValue)

renderResultPredicateTreeCondition :: IndexedResultPredicateTree -> Text
renderResultPredicateTreeCondition predicateTree =
  case predicateTree of
    IndexedResultPredicateLeaf predicateLeaf ->
      renderResultPredicateLeafCondition predicateLeaf
    IndexedResultPredicateAnd predicateValues ->
      "(" <> T.intercalate " AND " (map renderResultPredicateTreeCondition predicateValues) <> ")"
    IndexedResultPredicateOr predicateValues ->
      "(" <> T.intercalate " OR " (map renderResultPredicateTreeCondition predicateValues) <> ")"
    IndexedResultPredicateNot predicateValue ->
      "NOT (" <> renderResultPredicateTreeCondition predicateValue <> ")"

renderResultPredicateLeafCondition :: ResolvedResultPredicateLeaf -> Text
renderResultPredicateLeafCondition predicateLeaf =
  let columnRef = resultPredicateKey predicateLeaf
   in case (resultPredicateOperator predicateLeaf, resultPredicateValue predicateLeaf) of
        (PredicateEquals, PredicateScalar scalarValue) -> columnRef <> " = " <> renderFilterLiteral scalarValue
        (PredicateNotEquals, PredicateScalar scalarValue) -> columnRef <> " <> " <> renderFilterLiteral scalarValue
        (PredicateGreaterThan, PredicateScalar scalarValue) -> columnRef <> " > " <> renderFilterLiteral scalarValue
        (PredicateGreaterThanOrEqual, PredicateScalar scalarValue) -> columnRef <> " >= " <> renderFilterLiteral scalarValue
        (PredicateLessThan, PredicateScalar scalarValue) -> columnRef <> " < " <> renderFilterLiteral scalarValue
        (PredicateLessThanOrEqual, PredicateScalar scalarValue) -> columnRef <> " <= " <> renderFilterLiteral scalarValue
        (PredicateIn, PredicateList values) -> columnRef <> " IN (" <> T.intercalate ", " (map renderFilterLiteral values) <> ")"
        (PredicateNotIn, PredicateList values) -> columnRef <> " NOT IN (" <> T.intercalate ", " (map renderFilterLiteral values) <> ")"
        (PredicateBetween, PredicateRange lowerValue upperValue) -> columnRef <> " BETWEEN " <> renderFilterLiteral lowerValue <> " AND " <> renderFilterLiteral upperValue
        _ -> error "Unsupported result predicate tree operator/value."

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

renderRowPredicateJoinClauses :: Text -> Maybe ResolvedRowPredicateTree -> [Text]
renderRowPredicateJoinClauses baseAlias maybePredicateTree =
  case maybePredicateTree of
    Nothing -> []
    Just predicateTree ->
      concatMap renderIndexedRowPredicateLeafJoin (indexedRowPredicateTreeLeaves (indexRowPredicateTree 1 predicateTree))
  where
    renderIndexedRowPredicateLeafJoin :: (Int, ResolvedRowPredicateLeaf) -> [Text]
    renderIndexedRowPredicateLeafJoin (indexValue, predicateLeaf) =
      if null (OG.steps (rowPredicatePath predicateLeaf))
        then []
        else
          renderPathJoinClauses
            "JOIN"
            baseAlias
            (rowPredicateAlias indexValue predicateLeaf)
            ("lf" <> T.pack (show indexValue) <> "p")
            (rowPredicatePath predicateLeaf)

renderRowPredicateConditions :: Text -> Maybe ResolvedRowPredicateTree -> [Text]
renderRowPredicateConditions _baseAlias maybePredicateTree =
  case maybePredicateTree of
    Nothing -> []
    Just predicateTree -> [renderRowPredicateTreeCondition (indexRowPredicateTree 1 predicateTree)]

indexRowPredicateTree :: Int -> ResolvedRowPredicateTree -> IndexedRowPredicateTree
indexRowPredicateTree startIndex predicateTree =
  fst (indexRowPredicateTreeFrom startIndex predicateTree)

indexRowPredicateTreeFrom :: Int -> ResolvedRowPredicateTree -> (IndexedRowPredicateTree, Int)
indexRowPredicateTreeFrom startIndex predicateTree =
  case predicateTree of
    ResolvedRowPredicateLeafNode predicateLeaf ->
      (IndexedRowPredicateLeaf startIndex predicateLeaf, startIndex + 1)
    ResolvedRowPredicateAnd predicateValues ->
      let (indexedValues, nextIndex) = indexRowPredicateChildren startIndex predicateValues
       in (IndexedRowPredicateAnd indexedValues, nextIndex)
    ResolvedRowPredicateOr predicateValues ->
      let (indexedValues, nextIndex) = indexRowPredicateChildren startIndex predicateValues
       in (IndexedRowPredicateOr indexedValues, nextIndex)
    ResolvedRowPredicateNot predicateValue ->
      let (indexedValue, nextIndex) = indexRowPredicateTreeFrom startIndex predicateValue
       in (IndexedRowPredicateNot indexedValue, nextIndex)

indexRowPredicateChildren :: Int -> [ResolvedRowPredicateTree] -> ([IndexedRowPredicateTree], Int)
indexRowPredicateChildren startIndex predicateValues =
  case predicateValues of
    [] -> ([], startIndex)
    predicateValue : remaining ->
      let (indexedValue, nextIndex) = indexRowPredicateTreeFrom startIndex predicateValue
          (indexedRemaining, finalIndex) = indexRowPredicateChildren nextIndex remaining
       in (indexedValue : indexedRemaining, finalIndex)

indexedRowPredicateTreeLeaves :: IndexedRowPredicateTree -> [(Int, ResolvedRowPredicateLeaf)]
indexedRowPredicateTreeLeaves predicateTree =
  case predicateTree of
    IndexedRowPredicateLeaf indexValue predicateLeaf -> [(indexValue, predicateLeaf)]
    IndexedRowPredicateAnd predicateValues -> concatMap indexedRowPredicateTreeLeaves predicateValues
    IndexedRowPredicateOr predicateValues -> concatMap indexedRowPredicateTreeLeaves predicateValues
    IndexedRowPredicateNot predicateValue -> indexedRowPredicateTreeLeaves predicateValue

renderRowPredicateTreeCondition :: IndexedRowPredicateTree -> Text
renderRowPredicateTreeCondition predicateTree =
  case predicateTree of
    IndexedRowPredicateLeaf indexValue predicateLeaf ->
      renderRowPredicateLeafCondition indexValue predicateLeaf
    IndexedRowPredicateAnd predicateValues ->
      "(" <> T.intercalate " AND " (map renderRowPredicateTreeCondition predicateValues) <> ")"
    IndexedRowPredicateOr predicateValues ->
      "(" <> T.intercalate " OR " (map renderRowPredicateTreeCondition predicateValues) <> ")"
    IndexedRowPredicateNot predicateValue ->
      "NOT (" <> renderRowPredicateTreeCondition predicateValue <> ")"

renderRowPredicateLeafCondition :: Int -> ResolvedRowPredicateLeaf -> Text
renderRowPredicateLeafCondition indexValue predicateLeaf =
  let columnRef = rowPredicateAlias indexValue predicateLeaf <> "." <> rowPredicateColumn predicateLeaf
   in case (rowPredicateOperator predicateLeaf, rowPredicateValue predicateLeaf) of
        (PredicateEquals, PredicateScalar scalarValue) -> columnRef <> " = " <> renderFilterLiteral scalarValue
        (PredicateNotEquals, PredicateScalar scalarValue) -> columnRef <> " <> " <> renderFilterLiteral scalarValue
        (PredicateGreaterThan, PredicateScalar scalarValue) -> columnRef <> " > " <> renderFilterLiteral scalarValue
        (PredicateGreaterThanOrEqual, PredicateScalar scalarValue) -> columnRef <> " >= " <> renderFilterLiteral scalarValue
        (PredicateLessThan, PredicateScalar scalarValue) -> columnRef <> " < " <> renderFilterLiteral scalarValue
        (PredicateLessThanOrEqual, PredicateScalar scalarValue) -> columnRef <> " <= " <> renderFilterLiteral scalarValue
        (PredicateIn, PredicateList values) -> columnRef <> " IN (" <> T.intercalate ", " (map renderFilterLiteral values) <> ")"
        (PredicateNotIn, PredicateList values) -> columnRef <> " NOT IN (" <> T.intercalate ", " (map renderFilterLiteral values) <> ")"
        (PredicateBetween, PredicateRange lowerValue upperValue) -> columnRef <> " BETWEEN " <> renderFilterLiteral lowerValue <> " AND " <> renderFilterLiteral upperValue
        (PredicateContains, PredicateScalar (FilterText textValue)) -> columnRef <> " ILIKE " <> renderLikeContainsLiteral textValue <> " ESCAPE '\\'"
        _ -> error "Unsupported row predicate tree operator/value."

rowPredicateAlias :: Int -> ResolvedRowPredicateLeaf -> Text
rowPredicateAlias indexValue predicateLeaf =
  if null (OG.steps (rowPredicatePath predicateLeaf))
    then "f"
    else "lf" <> T.pack (show indexValue)

renderLikeContainsLiteral :: Text -> Text
renderLikeContainsLiteral rawValue =
  "'%" <> escapeLikePattern rawValue <> "%'"

escapeLikePattern :: Text -> Text
escapeLikePattern =
  T.replace "_" "\\_" . T.replace "%" "\\%" . T.replace "\\" "\\\\" . escapeSqlLiteral

escapeSqlLiteral :: Text -> Text
escapeSqlLiteral = T.replace "'" "''"

renderFilterLiteral :: FilterValue -> Text
renderFilterLiteral filterValue =
  case filterValue of
    FilterInt intValue -> T.pack (show intValue)
    FilterDouble doubleValue -> T.pack (show doubleValue)
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
