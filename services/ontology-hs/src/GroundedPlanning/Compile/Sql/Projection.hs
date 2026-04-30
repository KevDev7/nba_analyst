{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Compile.Sql.Projection
  ( renderDisplayMetricAggregateSelectLines
  , renderDisplayMetricDirectSelectLines
  , renderDisplayMetricFinalSelectLines
  , renderDisplayMetricSourceSelectLines
  , renderMetadataAggregateSelectLines
  , renderMetadataDirectSelectLines
  , renderMetadataFinalSelectLines
  , renderMetadataSourceSelectLines
  , renderMetricValue
  , renderResultPredicateAggregateSelectLines
  , renderResultPredicateDirectSelectLines
  , renderResultPredicateFinalSelectLines
  , renderResultPredicateSourceSelectLines
  ) where

import Data.Text (Text)
import GroundedPlanning.Compile.Sql.Common.Primitives (renderColumnRefWithContext)
import GroundedPlanning.Resolve

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

compileResultPredicateAggregation :: ResolvedResultPredicateLeaf -> Text
compileResultPredicateAggregation predicateLeaf =
  case resultPredicateAggregation predicateLeaf of
    "sum" -> "SUM(__" <> resultPredicateKey predicateLeaf <> "_source)"
    "avg" -> "ROUND(AVG(__" <> resultPredicateKey predicateLeaf <> "_source), 1)"
    "identity" -> "MAX(__" <> resultPredicateKey predicateLeaf <> "_source)"
    _ -> error "Unsupported result-predicate aggregation."

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
