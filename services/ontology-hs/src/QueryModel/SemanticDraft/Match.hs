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
  , requireTimeScopeFactSurface
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
import QueryModel.SemanticDraft.MeasureMatch
import QueryModel.SemanticDraft.Normalize
import QueryModel.SemanticDraft.Types (TimeScope (AllAvailable, DateRange, ExactSeason, LastNDays, PastYear, RecentGames, SeasonTypeOnly))

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

requireTimeScopeFactSurface :: TimeScope -> Object -> Maybe ()
requireTimeScopeFactSurface timeScopeValue factObjectValue =
  case timeScopeValue of
    RecentGames _ seasonFilters -> do
      _ <- findAttribute factObjectValue "game_date"
      case seasonFilters of
        [] -> Just ()
        _ -> do
          _ <- findAttribute factObjectValue "season_year"
          _ <- findAttribute factObjectValue "season_type"
          Just ()
    ExactSeason _ _ -> do
      _ <- findAttribute factObjectValue "season_year"
      _ <- findAttribute factObjectValue "season_type"
      case findAttribute factObjectValue "game_date" of
        Nothing -> Just ()
        Just _ -> Nothing
    SeasonTypeOnly _ -> do
      _ <- findAttribute factObjectValue "season_type"
      Just ()
    LastNDays _ -> do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    PastYear -> do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    DateRange _ _ -> do
      _ <- findAttribute factObjectValue "game_date"
      Just ()
    AllAvailable -> do
      _ <- findAttribute factObjectValue "game_date"
      Just ()

bestMetricMatch :: Text -> Object -> Maybe OT.MetricDef
bestMetricMatch =
  bestExecutableMetricMatch

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
