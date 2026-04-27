{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Find (compileFindSql) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common
import GroundedPlanning.Resolve
import OntologyLayer.Graph (DiscoveredPath)
import qualified OntologyLayer.Graph as OG
import QueryModel.IR (Filter, filterIntValue, filterKindText, filterTextValue)

compileFindSql :: ResolvedFindQuery -> Text
compileFindSql resolved =
  let
    ResolvedFindQuery
      { resolvedFindFactTableName = factTableNameValue
      , resolvedFindTargetPath = targetPathValue
      , resolvedFindDisplays = displayValues
      , resolvedFindPredicates = predicateValues
      , resolvedFindFilters = findFilterValues
      , resolvedFindLimit = maybeFindLimit
      } = resolved
    selectLines = renderFindSelectLines displayValues predicateValues
    predicateJoinLines = concatMap renderIndexedFindPredicateJoin (zip [1 :: Int ..] predicateValues)
    whereConditions =
      map renderIndexedFindPredicateCondition (zip [1 :: Int ..] predicateValues)
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
          <> predicateJoinLines
          <> [ "  WHERE " <> combineWhereClauses whereConditions
             , ")"
             , "SELECT DISTINCT " <> T.intercalate ", " (findSelectedLabels displayValues predicateValues)
             , "FROM filtered_find_rows"
             , "WHERE __find_row_rank <= " <> T.pack (show gamesValue)
             , "ORDER BY " <> findOrderColumn displayValues
             ]
          <> limitClause maybeFindLimit
    Nothing ->
      T.unlines $
        [ "SELECT DISTINCT"
        ]
          <> selectLines
          <> [ "FROM " <> factTableNameValue <> " f" ]
          <> renderPathJoinClauses "JOIN" "f" "r" "fp" targetPathValue
          <> predicateJoinLines
          <> [ "WHERE " <> combineWhereClauses whereConditions
             , "ORDER BY " <> findOrderColumn displayValues
             ]
          <> limitClause maybeFindLimit

renderFindSelectLines :: [ResolvedFindDisplay] -> [ResolvedFindPredicate] -> [Text]
renderFindSelectLines displayValues predicateValues =
  map renderDisplay (markLast (displaySelections <> predicateSelections))
  where
    displaySelections =
      [ (displayLabel displayValue, findPathAlias "r" (displayPath displayValue), displayColumn displayValue)
      | displayValue <- displayValues
      ]
    predicateSelections =
      [ (predicateLabel predicateValue, findPredicateAlias indexValue predicateValue, predicateColumn predicateValue)
      | (indexValue, predicateValue) <- zip [1 :: Int ..] predicateValues
      , predicateLabel predicateValue `notElem` map displayLabel displayValues
      ]
    renderDisplay (isLastValue, (labelValue, aliasValue, columnValue)) =
      "  " <> aliasValue <> "." <> columnValue <> " AS " <> labelValue <> if isLastValue then "" else ","

indentFindSelectLines :: [Text] -> [Text]
indentFindSelectLines selectLines =
  map ensureComma selectLines
  where
    ensureComma lineValue =
      let indentedLine = "  " <> lineValue
       in if "," `T.isSuffixOf` indentedLine
            then indentedLine
            else indentedLine <> ","

findSelectedLabels :: [ResolvedFindDisplay] -> [ResolvedFindPredicate] -> [Text]
findSelectedLabels displayValues predicateValues =
  displayLabels <> predicateLabels
  where
    displayLabels = map displayLabel displayValues
    predicateLabels =
      [ predicateLabel predicateValue
      | predicateValue <- predicateValues
      , predicateLabel predicateValue `notElem` displayLabels
      ]

markLast :: [a] -> [(Bool, a)]
markLast values =
  case values of
    [] -> []
    [value] -> [(True, value)]
    value : remaining -> (False, value) : markLast remaining

renderIndexedFindPredicateJoin :: (Int, ResolvedFindPredicate) -> [Text]
renderIndexedFindPredicateJoin (indexValue, predicateValue) =
  if null (OG.steps (predicatePath predicateValue))
    then []
    else renderPathJoinClauses "JOIN" "f" (findPredicateAlias indexValue predicateValue) ("pr" <> T.pack (show indexValue) <> "p") (predicatePath predicateValue)

renderIndexedFindPredicateCondition :: (Int, ResolvedFindPredicate) -> Text
renderIndexedFindPredicateCondition (indexValue, predicateValueResolved) =
  findPredicateAlias indexValue predicateValueResolved
    <> "."
    <> predicateColumn predicateValueResolved
    <> " "
    <> predicateOp predicateValueResolved
    <> " "
    <> renderFilterLiteral (predicateValue predicateValueResolved)

findPredicateAlias :: Int -> ResolvedFindPredicate -> Text
findPredicateAlias indexValue predicateValue =
  findPathAlias ("pr" <> T.pack (show indexValue)) (predicatePath predicateValue)

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
  mapMaybeFindFilterCondition filterValues
  where
    latestDateSubquery = "(SELECT MAX(game_date) FROM " <> findFactTableName <> ")"
    mapMaybeFindFilterCondition [] = []
    mapMaybeFindFilterCondition (filterValue : remaining) =
      case filterKindText filterValue of
        "last_n_games" -> mapMaybeFindFilterCondition remaining
        "past_year" ->
          ("f.game_date >= " <> latestDateSubquery <> " - INTERVAL '1 year'") : mapMaybeFindFilterCondition remaining
        "exact_season" ->
          case filterTextValue filterValue of
            Just seasonLabelValue -> ("f.season_year = '" <> escapeSqlLiteral seasonLabelValue <> "'") : mapMaybeFindFilterCondition remaining
            Nothing -> mapMaybeFindFilterCondition remaining
        "season_type" ->
          case filterTextValue filterValue of
            Just seasonTypeValue -> ("f.season_type = '" <> escapeSqlLiteral seasonTypeValue <> "'") : mapMaybeFindFilterCondition remaining
            Nothing -> mapMaybeFindFilterCondition remaining
        _ -> mapMaybeFindFilterCondition remaining
