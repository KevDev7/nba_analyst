{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.MeasureMatch
  ( bestExecutableMetricMatch
  , bestPublicMeasureAttributeMatch
  , metricAliases
  , metricMatchScore
  , measureAttributeScore
  ) where

import Data.List (nub, sortOn)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Types
  ( AttributeKind (Measure)
  , AttributeVisibility (Public)
  , Object
  )
import qualified OntologyLayer.Types as OT
import QueryModel.SemanticConstruction.MatchAccessors
import QueryModel.SemanticDraft.Normalize (normalizedKey, normalizedMeasureKey)

bestExecutableMetricMatch :: Text -> Object -> Maybe OT.MetricDef
bestExecutableMetricMatch rawMeasure objectValue =
  case sortOn metricRank matchingMetrics of
    metricValue : _ -> Just metricValue
    [] -> Nothing
  where
    matchingMetrics =
      [ metricValue
      | metricValue <- objectMetrics objectValue
      , metricExecutable metricValue
      , metricMatchScore rawMeasure metricValue > 0
      ]
    metricRank metricValue =
      (Down (metricMatchScore rawMeasure metricValue), metricName metricValue)

bestPublicMeasureAttributeMatch :: Text -> Object -> Maybe OT.Attribute
bestPublicMeasureAttributeMatch rawField objectValue =
  case sortOn attributeRank matches of
    attributeValue : _ -> Just attributeValue
    [] -> Nothing
  where
    matches =
      [ attributeValue
      | attributeValue <- objectAttributes objectValue
      , attributeKind attributeValue == Measure
      , attributeVisibility attributeValue == Public
      , measureAttributeScore rawField objectValue attributeValue > 0
      ]
    attributeRank attributeValue =
      ( Down (measureAttributeScore rawField objectValue attributeValue)
      , attributeName attributeValue
      )

metricMatchScore :: Text -> OT.MetricDef -> Int
metricMatchScore rawMeasure metricValue =
  maximum (0 : [score | (aliasKey, score) <- metricAliases metricValue, aliasKey == measureKey])
  where
    measureKey = normalizedMeasureKey rawMeasure

metricAliases :: OT.MetricDef -> [(Text, Int)]
metricAliases metricValue =
  baseAliases <> aggregationAliases <> sourceAliases
  where
    metricKey = normalizedMeasureKey (metricName metricValue)
    sourceKeys = map normalizedMeasureKey (metricSourceAttributes metricValue)
    aggregationKey = normalizedKey (metricAggregation metricValue)
    baseAliases =
      (metricKey, 100)
        : aliasMetricKey metricKey
    sourceAliases =
      [ (sourceKey, 80)
      | sourceKey <- sourceKeys
      , aggregationKey `elem` ["sum", "identity"]
      ]
    aggregationAliases =
      concatMap (aliasesForAggregation aggregationKey metricKey) sourceKeys

aliasMetricKey :: Text -> [(Text, Int)]
aliasMetricKey metricKey =
  [ (T.replace "total" "" metricKey, 75)
  | "total" `T.isInfixOf` metricKey
  , T.replace "total" "" metricKey /= ""
  ]
    <> [ ("total" <> T.dropEnd 5 metricKey, 95)
       | "total" `T.isSuffixOf` metricKey
       , T.dropEnd 5 metricKey /= ""
       ]
    <> [ ("winpct", 95)
       | metricKey == "winpercentage"
       ]
    <> [ ("winningpercentage", 95)
       | metricKey == "winpercentage"
       ]
    <> [ ("wins", 95)
       | metricKey == "gameswon"
       ]
    <> [ ("losses", 95)
       | metricKey == "gameslost"
       ]
    <> [ ("starts", 95)
       | metricKey == "gamesstarted"
       ]

aliasesForAggregation :: Text -> Text -> Text -> [(Text, Int)]
aliasesForAggregation aggregationKey metricKey sourceKey
  | aggregationKey == "avg" =
      [ ("average" <> sourceKey, 95)
      , ("avg" <> sourceKey, 95)
      , (sourceKey <> "pergame", 90)
      , ("pergame" <> sourceKey, 85)
      ]
        <> pointsAverageAliases
        <> minutesAverageAliases
  | aggregationKey == "sum" =
      [ ("total" <> sourceKey, 95)
      ]
        <> pointsTotalAliases
        <> minutesTotalAliases
  | "pergame" `T.isSuffixOf` metricKey =
      concatMap perGameAliases perGameBaseKeys
        <> pointsAverageAliases
        <> minutesAverageAliases
  | otherwise = []
  where
    perGameBaseKeys =
      nub
        [ baseKey
        | key <- [sourceKey, metricKey]
        , Just baseKey <- [T.stripSuffix "pergame" key]
        , baseKey /= ""
        ]
    perGameAliases baseKey =
      [ ("average" <> baseKey, 95)
      , ("avg" <> baseKey, 95)
      , (baseKey <> "pergame", 95)
      ]
    pointsAverageAliases =
      if sourceKey `elem` ["points", "score"]
        then [("ppg", 95), ("averagepoints", 95), ("avgpoints", 95), ("averagescoring", 90)]
        else []
    pointsTotalAliases =
      if sourceKey `elem` ["points", "score"]
        then
          [ ("points", 85)
          , ("pts", 85)
          , ("scoring", 80)
          , ("scoringtotal", 95)
          , ("scoringtotals", 95)
          , ("pointtotal", 95)
          , ("pointtotals", 95)
          , ("pointstotal", 95)
          , ("pointstotals", 95)
          ]
        else []
    minutesAverageAliases =
      if sourceKey `elem` ["minutes", "minutesplayed", "minutespergame"] || "minutes" `T.isInfixOf` metricKey
        then
          [ ("minutes", 85)
          , ("mins", 85)
          , ("mp", 85)
          , ("minutesplayed", 90)
          , ("averageminutes", 95)
          , ("avgminutes", 95)
          , ("minutespergame", 95)
          , ("minutespg", 90)
          , ("mpg", 90)
          ]
        else []
    minutesTotalAliases =
      if sourceKey `elem` ["minutes", "minutesplayed"] || "minutes" `T.isInfixOf` metricKey
        then
          [ ("minutes", 80)
          , ("mins", 80)
          , ("totalminutes", 95)
          , ("minutesplayed", 85)
          ]
        else []

measureAttributeScore :: Text -> Object -> OT.Attribute -> Int
measureAttributeScore rawField objectValue attributeValue =
  maximum
    ( 0
        : [ score
          | rawAliasKey <- rawAliasKeys
          , (attributeAlias, score) <- attributeAliases
          , rawAliasKey == attributeAlias
          ]
        <> suffixScores
    )
  where
    rawKey = normalizedMeasureKey rawField
    rawAliasKeys = nub [rawKey, T.replace "team" "" rawKey, T.replace "player" "" rawKey]
    objectKey = normalizedKey (objectName objectValue)
    attributeKey = normalizedMeasureKey (attributeName attributeValue)
    attributeAliases =
      nub $
        [ (attributeKey, 100)
        , (T.replace objectKey "" attributeKey, 95)
        , (T.replace "team" "" attributeKey, 90)
        , (T.replace "player" "" attributeKey, 90)
        , (T.replace "opponent" "" attributeKey, 90)
        , (T.replace "played" "" attributeKey, 90)
        , (T.replace "total" "" attributeKey, 90)
        , (T.replace "percentage" "pct" attributeKey, 95)
        ]
          <> pointsAttributeAliases attributeKey
          <> minutesAttributeAliases attributeKey
    suffixScores =
      [ 80
      | rawKeyValue <- rawAliasKeys
      , rawKeyValue /= ""
      , rawKeyValue `T.isSuffixOf` attributeKey
      ]

pointsAttributeAliases :: Text -> [(Text, Int)]
pointsAttributeAliases attributeKey =
  if attributeKey `elem` ["points", "score"]
    then [("points", 85), ("pts", 85), ("scoring", 80), ("scored", 80)]
    else []

minutesAttributeAliases :: Text -> [(Text, Int)]
minutesAttributeAliases attributeKey =
  if "minutes" `T.isInfixOf` attributeKey
    then
      [ ("minutes", 90)
      , ("mins", 90)
      , ("mp", 90)
      , ("minutesplayed", 95)
      , ("minutespergame", 95)
      , ("mpg", 90)
      ]
    else []
