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
  , renderMaybeColumnRef
  , renderMaybePathJoinClauses
  , renderPathJoinClauses
  , renderResultPredicateConditions
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
import GroundedPlanning.Compile.Sql.Common.Primitives
import GroundedPlanning.Compile.Sql.Predicates (renderPredicateCondition)
import OntologyLayer.Graph (DiscoveredPath)
import qualified OntologyLayer.Graph as OG
import QueryModel.IR (Filter, filterIntValue, filterKindText, filterTextValue)

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
    "count_win" -> "SUM(CASE WHEN metric_source = 'win' THEN 1 ELSE 0 END)"
    "count_loss" -> "SUM(CASE WHEN metric_source = 'loss' THEN 1 ELSE 0 END)"
    "count_true" -> "SUM(CASE WHEN metric_source THEN 1 ELSE 0 END)"
    _ -> error "Unsupported executable metric aggregation."

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
   in case renderPredicateCondition columnRef (resultPredicateOperator predicateLeaf) (resultPredicateValue predicateLeaf) of
        Just conditionValue -> conditionValue
        Nothing -> error "Unsupported result predicate tree operator/value."

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
   in case renderPredicateCondition columnRef (rowPredicateOperator predicateLeaf) (rowPredicateValue predicateLeaf) of
        Just conditionValue -> conditionValue
        Nothing -> error "Unsupported row predicate tree operator/value."

rowPredicateAlias :: Int -> ResolvedRowPredicateLeaf -> Text
rowPredicateAlias indexValue predicateLeaf =
  if null (OG.steps (rowPredicatePath predicateLeaf))
    then "f"
    else "lf" <> T.pack (show indexValue)

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
