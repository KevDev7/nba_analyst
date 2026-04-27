{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.Match
  ( attributeKind
  , attributeName
  , attributeVisibility
  , bestMetricMatch
  , bestPublicDimensionMatch
  , identityDimension
  , metricAggregation
  , metricAliases
  , metricExecutable
  , metricMatchScore
  , metricName
  , metricSourceAttributes
  , objectAttributes
  , objectMetrics
  , objectName
  , requireRankingFactSurface
  , resolveSubjectObject
  , subjectFactAffinity
  , trendDimensionMatchesSubject
  , trendFactAffinity
  ) where

import Data.List (sortOn)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types
  ( AttributeKind (Dimension)
  , AttributeVisibility (Public)
  , Object
  , Ontology (objects)
  )
import qualified OntologyLayer.Types as OT
import QueryModel.SemanticDraft.Normalize
import QueryModel.SemanticDraft.Types (RankingFilterBundle (RecentRanking, SeasonRanking))

bestPublicDimensionMatch :: Text -> Object -> Maybe Text
bestPublicDimensionMatch rawDimension objectValue =
  case sortOn publicDimensionRank matchingDimensions of
    attributeValue : _ -> Just (attributeName attributeValue)
    [] -> Nothing
  where
    rawKey = normalizedKey rawDimension
    objectPrefix = normalizedKey (objectName objectValue)
    matchingDimensions =
      [ attributeValue
      | attributeValue <- objectAttributes objectValue
      , attributeKind attributeValue == Dimension
      , attributeVisibility attributeValue == Public
      , publicDimensionScore rawKey objectPrefix (attributeName attributeValue) > 0
      ]
    publicDimensionRank attributeValue =
      ( Down (publicDimensionScore rawKey objectPrefix (attributeName attributeValue))
      , attributeName attributeValue
      )

publicDimensionScore :: Text -> Text -> Text -> Int
publicDimensionScore rawKey objectPrefix attributeNameValue
  | rawKey == attributeKey = 100
  | rawKey == T.replace objectPrefix "" attributeKey = 95
  | rawKey == T.replace "primary" "" attributeKey = 90
  | rawKey `T.isSuffixOf` attributeKey = 80
  | otherwise = 0
  where
    attributeKey = normalizedKey attributeNameValue

trendDimensionMatchesSubject :: Object -> Text -> Bool
trendDimensionMatchesSubject subjectObject rawDimension =
  let rawKey = normalizedKey rawDimension
      subjectKey = subjectMatchKey (objectName subjectObject)
   in subjectMatchKey rawDimension == subjectKey
        || (subjectKey `T.isInfixOf` rawKey && "name" `T.isInfixOf` rawKey)

resolveSubjectObject :: Ontology -> Text -> Either Text Object
resolveSubjectObject ontology rawSubject =
  -- Map user-facing subject text to an ontology object.
  -- Example: "players" -> Player, "teams" -> Team.
  case matchingObjects of
    [objectValue] -> Right objectValue
    [] -> Left ("No ontology object matched draft subject '" <> rawSubject <> "'.")
    matches ->
      Left
        ( "Draft subject '"
            <> rawSubject
            <> "' is ambiguous across ontology objects: "
            <> T.intercalate ", " (map objectName matches)
            <> "."
        )
  where
    subjectKey = subjectMatchKey rawSubject
    matchingObjects =
      [ objectValue
      | objectValue <- objects ontology
      , subjectMatchKey (objectName objectValue) == subjectKey
      ]

subjectFactAffinity :: Object -> Object -> Int
subjectFactAffinity subjectObject factObjectValue =
  -- Prefer fact objects whose name contains the subject name, like PlayerGame for Player.
  if normalizedKey (objectName subjectObject) `T.isInfixOf` normalizedKey (objectName factObjectValue)
    then 100
    else 0

trendFactAffinity :: Text -> Object -> Object -> Int
trendFactAffinity trendGrain subjectObject factObjectValue =
  subjectFactAffinity subjectObject factObjectValue + grainSurfaceScore
  where
    grainSurfaceScore =
      case (trendGrain, findAttribute factObjectValue "game_date") of
        ("season", Nothing) -> 50
        ("season", Just _) -> 0
        (_, Just _) -> 50
        _ -> 0

requireRankingFactSurface :: RankingFilterBundle -> Object -> Maybe ()
requireRankingFactSurface rankingFilters factObjectValue =
  case rankingFilters of
    RecentRanking _ seasonFilters -> do
      _ <- findAttribute factObjectValue "game_date"
      case seasonFilters of
        [] -> Just ()
        _ -> do
          _ <- findAttribute factObjectValue "season_year"
          _ <- findAttribute factObjectValue "season_type"
          Just ()
    SeasonRanking _ _ -> do
      _ <- findAttribute factObjectValue "season_year"
      _ <- findAttribute factObjectValue "season_type"
      case findAttribute factObjectValue "game_date" of
        Nothing -> Just ()
        Just _ -> Nothing

bestMetricMatch :: Text -> Object -> Maybe OT.MetricDef
bestMetricMatch rawMeasure objectValue =
  -- Choose the highest-scoring executable ontology metric for the user's measure phrase.
  case rankedExecutableMatches of
    metricValue : _ -> Just metricValue
    [] -> Nothing
  where
    rankedExecutableMatches =
      sortOn
        (\metricValue -> Down (metricMatchScore rawMeasure metricValue))
        [ metricValue
        | metricValue <- objectMetrics objectValue
        , metricExecutable metricValue
        , metricMatchScore rawMeasure metricValue > 0
        ]

metricMatchScore :: Text -> OT.MetricDef -> Int
metricMatchScore rawMeasure metricValue =
  -- Score how well a user-facing measure phrase maps to one ontology metric.
  maximum (0 : [score | (aliasKey, score) <- metricAliases metricValue, aliasKey == measureKey])
  where
    measureKey = normalizedMeasureKey rawMeasure

metricAliases :: OT.MetricDef -> [(Text, Int)]
metricAliases metricValue =
  -- Generate lexical aliases for a metric from its name, aggregation, and source attributes.
  -- Example: total_points can match "points", "pts", "scoring", or "total points".
  baseAliases <> aggregationAliases <> sourceAliases
  where
    metricKey = normalizedMeasureKey (metricName metricValue)
    sourceKeys = map normalizedMeasureKey (metricSourceAttributes metricValue)
    aggregationKey = normalizedKey (metricAggregation metricValue)
    baseAliases =
      (metricKey, 100)
        : [ (T.replace "total" "" metricKey, 75)
          | "total" `T.isInfixOf` metricKey
          , T.replace "total" "" metricKey /= ""
          ]
          <> [ ("total" <> T.dropEnd 5 metricKey, 95)
             | "total" `T.isSuffixOf` metricKey
             , T.dropEnd 5 metricKey /= ""
             ]
    sourceAliases =
      [ (sourceKey, 80)
      | sourceKey <- sourceKeys
      , aggregationKey `elem` ["sum", "identity"]
      ]
    aggregationAliases =
      concatMap (aliasesForAggregation aggregationKey metricKey) sourceKeys

aliasesForAggregation :: Text -> Text -> Text -> [(Text, Int)]
aliasesForAggregation aggregationKey metricKey sourceKey
  -- Add measure aliases based on aggregation style, like avg points -> average_points.
  | aggregationKey == "avg" =
      [ ("average" <> sourceKey, 95)
      , ("avg" <> sourceKey, 95)
      , (sourceKey <> "pergame", 90)
      , ("pergame" <> sourceKey, 85)
      ]
        <> pointsAverageAliases
  | aggregationKey == "sum" =
      [ ("total" <> sourceKey, 95)
      ]
        <> pointsTotalAliases
  | "pergame" `T.isSuffixOf` metricKey =
      [ ("average" <> sourceKey, 95)
      , ("avg" <> sourceKey, 95)
      , (sourceKey <> "pergame", 95)
      ]
        <> pointsAverageAliases
  | otherwise = []
  where
    pointsAverageAliases =
      if sourceKey `elem` ["points", "score"] || "points" `T.isInfixOf` metricKey
        then [("ppg", 95), ("averagepoints", 95), ("avgpoints", 95), ("averagescoring", 90)]
        else []
    pointsTotalAliases =
      if sourceKey `elem` ["points", "score"] || "points" `T.isInfixOf` metricKey
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

identityDimension :: Object -> Maybe Text
identityDimension objectValue =
  -- Pick the best public dimension to display for the subject row.
  -- Example: Player prefers full_name; Team prefers team_name.
  case sortOn identityRank publicDimensions of
    attributeValue : _ -> Just (attributeName attributeValue)
    [] -> Nothing
  where
    publicDimensions =
      [ attributeValue
      | attributeValue <- objectAttributes objectValue
      , attributeKind attributeValue == Dimension
      , attributeVisibility attributeValue == Public
      ]
    objectPrefix = normalizedKey (objectName objectValue)
    identityRank attributeValue =
      let attributeKey = normalizedKey (attributeName attributeValue)
       in if attributeKey == "fullname"
            then (0 :: Int, attributeKey)
            else
              if attributeKey == objectPrefix <> "name"
                then (1, attributeKey)
                else
                  if "name" `T.isSuffixOf` attributeKey
                    then (2, attributeKey)
                    else (3, attributeKey)

objectName :: Object -> Text
objectName OT.Object {OT.name = currentName} = currentName

objectAttributes :: Object -> [OT.Attribute]
objectAttributes OT.Object {OT.attributes = currentAttributes} = currentAttributes

objectMetrics :: Object -> [OT.MetricDef]
objectMetrics OT.Object {OT.metrics = currentMetrics} = currentMetrics

attributeName :: OT.Attribute -> Text
attributeName OT.Attribute {OT.name = currentName} = currentName

attributeKind :: OT.Attribute -> AttributeKind
attributeKind OT.Attribute {OT.kind = currentKind} = currentKind

attributeVisibility :: OT.Attribute -> AttributeVisibility
attributeVisibility OT.Attribute {OT.visibility = currentVisibility} = currentVisibility

metricName :: OT.MetricDef -> Text
metricName OT.MetricDef {OT.name = currentName} = currentName

metricAggregation :: OT.MetricDef -> Text
metricAggregation OT.MetricDef {OT.aggregation = currentAggregation} = currentAggregation

metricSourceAttributes :: OT.MetricDef -> [Text]
metricSourceAttributes OT.MetricDef {OT.source_attributes = currentSourceAttributes} = currentSourceAttributes

metricExecutable :: OT.MetricDef -> Bool
metricExecutable OT.MetricDef {OT.executable = currentExecutable} = currentExecutable
