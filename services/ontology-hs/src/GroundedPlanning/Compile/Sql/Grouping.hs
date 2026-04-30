{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Grouping
  ( groupingAlias
  , primaryGroupingKey
  , renderGroupingAggregateSelectLines
  , renderGroupingFinalSelectLines
  , renderGroupingJoinClauses
  , renderGroupingKeys
  , renderGroupingOrder
  , renderGroupingSource
  , renderGroupingSourceSelectLines
  ) where

import Data.Text (Text)
import qualified Data.Text as T
import GroundedPlanning.Compile.Sql.Common (renderPathJoinClauses)
import GroundedPlanning.Resolve
import qualified OntologyLayer.Graph as OG

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
