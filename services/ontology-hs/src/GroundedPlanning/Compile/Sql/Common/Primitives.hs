{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Common.Primitives
  ( combineWhereClauses
  , escapeLikePattern
  , escapeSqlLiteral
  , limitClause
  , renderColumnRefWithContext
  , renderFactExpression
  , renderFilterLiteral
  , renderLikeContainsLiteral
  , renderMaybeColumnRef
  , renderWhereLines
  , stripLastTrailingComma
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Resolve (ColumnRef, columnName, tableRole)
import QueryModel.IR (FilterValue (FilterDouble, FilterInt, FilterText))

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

renderWhereLines :: Text -> [Text] -> [Text]
renderWhereLines prefix conditions =
  case conditions of
    [] -> []
    _ -> [prefix <> "WHERE " <> combineWhereClauses conditions]

stripLastTrailingComma :: [Text] -> [Text]
stripLastTrailingComma sourceLines =
  case reverse sourceLines of
    [] -> []
    lastLine : earlierLines ->
      reverse earlierLines
        <> [ case T.stripSuffix "," lastLine of
               Just strippedLine -> strippedLine
               Nothing -> lastLine
           ]

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
