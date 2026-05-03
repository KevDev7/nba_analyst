{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Find (compileFindSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
  ( renderGameDateFilterConditions
  , renderPathJoinClauses
  )
import GroundedPlanning.Compile.Sql.Common.Primitives
  ( limitClause
  , renderFactExpression
  , renderWhereLines
  )
import GroundedPlanning.Compile.Sql.Predicates (renderPredicateCondition)
import GroundedPlanning.Resolve
import OntologyLayer.Graph (DiscoveredPath)
import qualified OntologyLayer.Graph as OG
import QueryModel.IR (Filter, FindOrderDirection (..), filterIntValue, filterKindText)

data IndexedFindPredicateTree
  = IndexedFindPredicateLeaf Int ResolvedFindPredicateLeaf
  | IndexedFindPredicateAnd [IndexedFindPredicateTree]
  | IndexedFindPredicateOr [IndexedFindPredicateTree]
  | IndexedFindPredicateNot IndexedFindPredicateTree

compileFindSql :: ResolvedFindQuery -> Text
compileFindSql resolved =
  let
    ResolvedFindQuery
      { resolvedFindFactTableName = factTableNameValue
      , resolvedFindTargetPath = targetPathValue
      , resolvedFindDisplays = displayValues
      , resolvedFindOrders = orderValues
      , resolvedFindPredicateTree = maybePredicateTree
      , resolvedFindFilters = findFilterValues
      , resolvedFindLimit = maybeFindLimit
      } = resolved
    indexedPredicateTree = indexFindPredicateTree 1 <$> maybePredicateTree
    predicateTreeLeaves =
      case indexedPredicateTree of
        Nothing -> []
        Just predicateTree -> indexedFindPredicateTreeLeaves predicateTree
    selectLines = renderFindSelectLines targetPathValue displayValues predicateTreeLeaves
    orderSelectLines = renderFindOrderSelectLines targetPathValue orderValues
    displayJoinLines = concatMap (renderIndexedFindDisplayJoin targetPathValue) (zip [1 :: Int ..] displayValues)
    orderJoinLines = concatMap (renderIndexedFindOrderJoin targetPathValue) (zip [1 :: Int ..] orderValues)
    predicateTreeJoinLines =
      concatMap renderIndexedFindPredicateLeafJoin predicateTreeLeaves
    whereConditions =
      maybe [] (\predicateTree -> [renderFindPredicateTreeCondition predicateTree]) indexedPredicateTree
        <> renderFindFilterConditions factTableNameValue findFilterValues
    maybeLastNGames = findLastNGames findFilterValues
   in
  case maybeLastNGames of
    Just gamesValue ->
      T.unlines $
        [ "WITH filtered_find_rows AS ("
        , "  SELECT"
        ]
          <> indentFindSelectLines selectLines
          <> indentFindSelectLines orderSelectLines
          <> [ "    f.game_date AS __find_game_date,"
             , "    ROW_NUMBER() OVER (ORDER BY f.game_date DESC) AS __find_row_rank"
             , "  FROM " <> factTableNameValue <> " f"
             ]
          <> renderPathJoinClauses "JOIN" "f" "r" "fp" targetPathValue
          <> displayJoinLines
          <> orderJoinLines
          <> predicateTreeJoinLines
          <> renderWhereLines "  " whereConditions
          <> [ ")"
             , "SELECT DISTINCT " <> T.intercalate ", " (findSelectedLabels displayValues predicateTreeLeaves)
             , "FROM filtered_find_rows"
             ]
          <> renderWhereLines "" ["__find_row_rank <= " <> T.pack (show gamesValue)]
          <> [ "ORDER BY " <> findOrderColumn targetPathValue displayValues orderValues True ]
          <> limitClause maybeFindLimit
    Nothing ->
      T.unlines $
        [ "SELECT DISTINCT"
        ]
          <> selectLines
          <> [ "FROM " <> factTableNameValue <> " f" ]
          <> renderPathJoinClauses "JOIN" "f" "r" "fp" targetPathValue
          <> displayJoinLines
          <> orderJoinLines
          <> predicateTreeJoinLines
          <> renderWhereLines "" whereConditions
          <> [ "ORDER BY " <> findOrderColumn targetPathValue displayValues orderValues False ]
          <> limitClause maybeFindLimit

renderFindSelectLines :: DiscoveredPath -> [ResolvedFindDisplay] -> [(Int, ResolvedFindPredicateLeaf)] -> [Text]
renderFindSelectLines targetPathValue displayValues predicateTreeLeaves =
  map renderDisplay (markLast (displaySelections <> predicateTreeSelections))
  where
    displaySelections =
      [ ( displayLabel displayValue
        , findDisplayAlias targetPathValue indexValue displayValue
        , displayColumn displayValue
        , displayExpression displayValue
        )
      | (indexValue, displayValue) <- zip [1 :: Int ..] displayValues
      ]
    predicateTreeSelections =
      uniqueSelectionsByLabel
        [ ( treePredicateLabel predicateValue
          , findPredicateTreeAlias indexValue predicateValue
          , treePredicateColumn predicateValue
          , treePredicateExpression predicateValue
          )
        | (indexValue, predicateValue) <- predicateTreeLeaves
        , treePredicateLabel predicateValue `notElem` map displayLabel displayValues
        ]
    renderDisplay (isLastValue, (labelValue, aliasValue, columnValue, maybeExpression)) =
      "  " <> renderFindValue aliasValue columnValue maybeExpression <> " AS " <> labelValue <> if isLastValue then "" else ","

renderFindOrderSelectLines :: DiscoveredPath -> [ResolvedFindOrder] -> [Text]
renderFindOrderSelectLines targetPathValue orderValues =
  map renderOrderSelect (zip [1 :: Int ..] orderValues)
  where
    renderOrderSelect (indexValue, orderValue) =
      "  "
        <> renderFindValue
          (findOrderAlias targetPathValue indexValue orderValue)
          (orderColumn orderValue)
          (orderExpression orderValue)
        <> " AS __find_order_"
        <> T.pack (show indexValue)
        <> ","

renderFindValue :: Text -> Text -> Maybe Text -> Text
renderFindValue aliasValue columnValue maybeExpression =
  case maybeExpression of
    Just expressionValue -> renderFactExpression aliasValue expressionValue
    Nothing -> aliasValue <> "." <> columnValue

uniqueSelectionsByLabel :: [(Text, Text, Text, Maybe Text)] -> [(Text, Text, Text, Maybe Text)]
uniqueSelectionsByLabel selections =
  case selections of
    [] -> []
    selection@(labelValue, _, _, _) : remaining ->
      selection : uniqueSelectionsByLabel [candidate | candidate@(candidateLabel, _, _, _) <- remaining, candidateLabel /= labelValue]

indentFindSelectLines :: [Text] -> [Text]
indentFindSelectLines selectLines =
  map ensureComma selectLines
  where
    ensureComma lineValue =
      let indentedLine = "  " <> lineValue
       in if "," `T.isSuffixOf` indentedLine
            then indentedLine
            else indentedLine <> ","

findSelectedLabels :: [ResolvedFindDisplay] -> [(Int, ResolvedFindPredicateLeaf)] -> [Text]
findSelectedLabels displayValues predicateTreeLeaves =
  displayLabels <> predicateTreeLabels
  where
    displayLabels = map displayLabel displayValues
    predicateTreeLabels =
      uniqueLabels
        [ treePredicateLabel predicateValue
        | (_, predicateValue) <- predicateTreeLeaves
        , treePredicateLabel predicateValue `notElem` displayLabels
        ]

uniqueLabels :: [Text] -> [Text]
uniqueLabels labels =
  case labels of
    [] -> []
    labelValue : remaining -> labelValue : uniqueLabels [candidate | candidate <- remaining, candidate /= labelValue]

markLast :: [a] -> [(Bool, a)]
markLast values =
  case values of
    [] -> []
    [value] -> [(True, value)]
    value : remaining -> (False, value) : markLast remaining

renderIndexedFindPredicateLeafJoin :: (Int, ResolvedFindPredicateLeaf) -> [Text]
renderIndexedFindPredicateLeafJoin (indexValue, predicateValue) =
  if null (OG.steps (treePredicatePath predicateValue))
    then []
    else renderPathJoinClauses "JOIN" "f" (findPredicateTreeAlias indexValue predicateValue) ("pt" <> T.pack (show indexValue) <> "p") (treePredicatePath predicateValue)

renderIndexedFindDisplayJoin :: DiscoveredPath -> (Int, ResolvedFindDisplay) -> [Text]
renderIndexedFindDisplayJoin targetPathValue (indexValue, displayValue)
  | null (OG.steps (displayPath displayValue)) = []
  | displayPath displayValue == targetPathValue = []
  | otherwise =
      renderPathJoinClauses
        "JOIN"
        "f"
        (findDisplayAlias targetPathValue indexValue displayValue)
        ("dp" <> T.pack (show indexValue) <> "p")
        (displayPath displayValue)

renderIndexedFindOrderJoin :: DiscoveredPath -> (Int, ResolvedFindOrder) -> [Text]
renderIndexedFindOrderJoin targetPathValue (indexValue, orderValue)
  | null (OG.steps (orderPath orderValue)) = []
  | orderPath orderValue == targetPathValue = []
  | otherwise =
      renderPathJoinClauses
        "JOIN"
        "f"
        (findOrderAlias targetPathValue indexValue orderValue)
        ("op" <> T.pack (show indexValue) <> "p")
        (orderPath orderValue)

findDisplayAlias :: DiscoveredPath -> Int -> ResolvedFindDisplay -> Text
findDisplayAlias targetPathValue indexValue displayValue
  | null (OG.steps (displayPath displayValue)) = "f"
  | displayPath displayValue == targetPathValue = "r"
  | otherwise = "d" <> T.pack (show indexValue)

findOrderAlias :: DiscoveredPath -> Int -> ResolvedFindOrder -> Text
findOrderAlias targetPathValue indexValue orderValue
  | null (OG.steps (orderPath orderValue)) = "f"
  | orderPath orderValue == targetPathValue = "r"
  | otherwise = "o" <> T.pack (show indexValue)

findPredicateTreeAlias :: Int -> ResolvedFindPredicateLeaf -> Text
findPredicateTreeAlias indexValue predicateValue =
  findPathAlias ("pt" <> T.pack (show indexValue)) (treePredicatePath predicateValue)

indexFindPredicateTree :: Int -> ResolvedFindPredicateTree -> IndexedFindPredicateTree
indexFindPredicateTree startIndex predicateTree =
  fst (indexFindPredicateTreeFrom startIndex predicateTree)

indexFindPredicateTreeFrom :: Int -> ResolvedFindPredicateTree -> (IndexedFindPredicateTree, Int)
indexFindPredicateTreeFrom startIndex predicateTree =
  case predicateTree of
    ResolvedFindPredicateLeafNode predicateLeaf ->
      (IndexedFindPredicateLeaf startIndex predicateLeaf, startIndex + 1)
    ResolvedFindPredicateAnd predicateValues ->
      let (indexedValues, nextIndex) = indexFindPredicateChildren startIndex predicateValues
       in (IndexedFindPredicateAnd indexedValues, nextIndex)
    ResolvedFindPredicateOr predicateValues ->
      let (indexedValues, nextIndex) = indexFindPredicateChildren startIndex predicateValues
       in (IndexedFindPredicateOr indexedValues, nextIndex)
    ResolvedFindPredicateNot predicateValue ->
      let (indexedValue, nextIndex) = indexFindPredicateTreeFrom startIndex predicateValue
       in (IndexedFindPredicateNot indexedValue, nextIndex)

indexFindPredicateChildren :: Int -> [ResolvedFindPredicateTree] -> ([IndexedFindPredicateTree], Int)
indexFindPredicateChildren startIndex predicateValues =
  case predicateValues of
    [] -> ([], startIndex)
    predicateValue : remaining ->
      let (indexedValue, nextIndex) = indexFindPredicateTreeFrom startIndex predicateValue
          (indexedRemaining, finalIndex) = indexFindPredicateChildren nextIndex remaining
       in (indexedValue : indexedRemaining, finalIndex)

indexedFindPredicateTreeLeaves :: IndexedFindPredicateTree -> [(Int, ResolvedFindPredicateLeaf)]
indexedFindPredicateTreeLeaves predicateTree =
  case predicateTree of
    IndexedFindPredicateLeaf indexValue predicateLeaf -> [(indexValue, predicateLeaf)]
    IndexedFindPredicateAnd predicateValues -> concatMap indexedFindPredicateTreeLeaves predicateValues
    IndexedFindPredicateOr predicateValues -> concatMap indexedFindPredicateTreeLeaves predicateValues
    IndexedFindPredicateNot predicateValue -> indexedFindPredicateTreeLeaves predicateValue

renderFindPredicateTreeCondition :: IndexedFindPredicateTree -> Text
renderFindPredicateTreeCondition predicateTree =
  case predicateTree of
    IndexedFindPredicateLeaf indexValue predicateLeaf ->
      renderFindPredicateLeafCondition indexValue predicateLeaf
    IndexedFindPredicateAnd predicateValues ->
      "(" <> T.intercalate " AND " (map renderFindPredicateTreeCondition predicateValues) <> ")"
    IndexedFindPredicateOr predicateValues ->
      "(" <> T.intercalate " OR " (map renderFindPredicateTreeCondition predicateValues) <> ")"
    IndexedFindPredicateNot predicateValue ->
      "NOT (" <> renderFindPredicateTreeCondition predicateValue <> ")"

renderFindPredicateLeafCondition :: Int -> ResolvedFindPredicateLeaf -> Text
renderFindPredicateLeafCondition indexValue predicateLeaf =
  let columnRef =
        renderFindValue
          (findPredicateTreeAlias indexValue predicateLeaf)
          (treePredicateColumn predicateLeaf)
          (treePredicateExpression predicateLeaf)
   in case renderPredicateCondition columnRef (treePredicateOperator predicateLeaf) (treePredicateValue predicateLeaf) of
        Just conditionValue -> conditionValue
        Nothing -> error "Unsupported find predicate tree operator/value."

findPathAlias :: Text -> DiscoveredPath -> Text
findPathAlias nonFactAlias pathValue =
  if null (OG.steps pathValue)
    then "f"
    else nonFactAlias

findOrderColumn :: DiscoveredPath -> [ResolvedFindDisplay] -> [ResolvedFindOrder] -> Bool -> Text
findOrderColumn targetPathValue displayValues orderValues useHiddenOrderAliases =
  case orderValues of
    [] ->
      case displayValues of
        displayValue : _ -> displayLabel displayValue <> " DESC"
        [] -> "1"
    _ -> T.intercalate ", " (map renderOrder (zip [1 :: Int ..] orderValues))
  where
    renderOrder (indexValue, orderValue) =
      renderOrderExpression indexValue orderValue <> " " <> directionText (orderDirection orderValue)
    renderOrderExpression indexValue orderValue =
      if useHiddenOrderAliases
        then "__find_order_" <> T.pack (show indexValue)
        else
          renderFindValue
            (findOrderAlias targetPathValue indexValue orderValue)
            (orderColumn orderValue)
            (orderExpression orderValue)
    directionText directionValue =
      case directionValue of
        FindOrderAsc -> "ASC"
        FindOrderDesc -> "DESC"

findLastNGames :: [Filter] -> Maybe Int
findLastNGames filterValues =
  case filterValues of
    [] -> Nothing
    filterValue : remaining ->
      if filterKindText filterValue == "last_n_games"
        then filterIntValue filterValue
        else findLastNGames remaining

renderFindFilterConditions :: Text -> [Filter] -> [Text]
renderFindFilterConditions findFactTableName filterValues =
  renderGameDateFilterConditions findFactTableName "f" filterValues
