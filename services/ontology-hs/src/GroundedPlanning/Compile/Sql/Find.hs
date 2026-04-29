{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Find (compileFindSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve
import OntologyLayer.Graph (DiscoveredPath)
import qualified OntologyLayer.Graph as OG
import QueryModel.IR (Filter, FilterValue (FilterText), PredicateOperator (..), PredicateValue (..), filterIntValue, filterKindText)

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
      , resolvedFindPredicateTree = maybePredicateTree
      , resolvedFindFilters = findFilterValues
      , resolvedFindLimit = maybeFindLimit
      } = resolved
    indexedPredicateTree = indexFindPredicateTree 1 <$> maybePredicateTree
    predicateTreeLeaves =
      case indexedPredicateTree of
        Nothing -> []
        Just predicateTree -> indexedFindPredicateTreeLeaves predicateTree
    selectLines = renderFindSelectLines displayValues predicateTreeLeaves
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
          <> [ "    f.game_date AS __find_game_date,"
             , "    ROW_NUMBER() OVER (ORDER BY f.game_date DESC) AS __find_row_rank"
             , "  FROM " <> factTableNameValue <> " f"
             ]
          <> renderPathJoinClauses "JOIN" "f" "r" "fp" targetPathValue
          <> predicateTreeJoinLines
          <> renderWhereLines "  " whereConditions
          <> [ ")"
             , "SELECT DISTINCT " <> T.intercalate ", " (findSelectedLabels displayValues predicateTreeLeaves)
             , "FROM filtered_find_rows"
             ]
          <> renderWhereLines "" ["__find_row_rank <= " <> T.pack (show gamesValue)]
          <> [ "ORDER BY " <> findOrderColumn displayValues ]
          <> limitClause maybeFindLimit
    Nothing ->
      T.unlines $
        [ "SELECT DISTINCT"
        ]
          <> selectLines
          <> [ "FROM " <> factTableNameValue <> " f" ]
          <> renderPathJoinClauses "JOIN" "f" "r" "fp" targetPathValue
          <> predicateTreeJoinLines
          <> renderWhereLines "" whereConditions
          <> [ "ORDER BY " <> findOrderColumn displayValues ]
          <> limitClause maybeFindLimit

renderWhereLines :: Text -> [Text] -> [Text]
renderWhereLines prefix conditions =
  case conditions of
    [] -> []
    _ -> [prefix <> "WHERE " <> combineWhereClauses conditions]

renderFindSelectLines :: [ResolvedFindDisplay] -> [(Int, ResolvedFindPredicateLeaf)] -> [Text]
renderFindSelectLines displayValues predicateTreeLeaves =
  map renderDisplay (markLast (displaySelections <> predicateTreeSelections))
  where
    displaySelections =
      [ (displayLabel displayValue, findPathAlias "r" (displayPath displayValue), displayColumn displayValue)
      | displayValue <- displayValues
      ]
    predicateTreeSelections =
      uniqueSelectionsByLabel
        [ (treePredicateLabel predicateValue, findPredicateTreeAlias indexValue predicateValue, treePredicateColumn predicateValue)
        | (indexValue, predicateValue) <- predicateTreeLeaves
        , treePredicateLabel predicateValue `notElem` map displayLabel displayValues
        ]
    renderDisplay (isLastValue, (labelValue, aliasValue, columnValue)) =
      "  " <> aliasValue <> "." <> columnValue <> " AS " <> labelValue <> if isLastValue then "" else ","

uniqueSelectionsByLabel :: [(Text, Text, Text)] -> [(Text, Text, Text)]
uniqueSelectionsByLabel selections =
  case selections of
    [] -> []
    selection@(labelValue, _, _) : remaining ->
      selection : uniqueSelectionsByLabel [candidate | candidate@(candidateLabel, _, _) <- remaining, candidateLabel /= labelValue]

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
  let columnRef = findPredicateTreeAlias indexValue predicateLeaf <> "." <> treePredicateColumn predicateLeaf
   in case (treePredicateOperator predicateLeaf, treePredicateValue predicateLeaf) of
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
        _ -> error "Unsupported find predicate tree operator/value."

renderLikeContainsLiteral :: Text -> Text
renderLikeContainsLiteral rawValue =
  "'%" <> escapeLikePattern rawValue <> "%'"

escapeLikePattern :: Text -> Text
escapeLikePattern =
  T.replace "_" "\\_" . T.replace "%" "\\%" . T.replace "\\" "\\\\" . escapeSqlLiteral

findPathAlias :: Text -> DiscoveredPath -> Text
findPathAlias nonFactAlias pathValue =
  if null (OG.steps pathValue)
    then "f"
    else nonFactAlias

findOrderColumn :: [ResolvedFindDisplay] -> Text
findOrderColumn displayValues =
  case displayValues of
    displayValue : _ -> displayLabel displayValue <> " DESC"
    [] -> "1"

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
