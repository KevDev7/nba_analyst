{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticConstruction.Grouping
  ( bestOntologyGroupingDimensionMatch
  , groupingIdentityDimension
  , requireGroupingDimensionReachable
  , resolveDefaultGroupingDimensions
  , resolveGroupingDimensionValue
  ) where

import Data.List (sortOn)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (Ontology (objects), Object)
import qualified OntologyLayer.Types as OT
import QueryModel.SemanticConstruction.Match
import QueryModel.SemanticConstruction.Types
import QueryModel.SemanticDraft.Normalize (normalizedKey)

resolveDefaultGroupingDimensions :: Ontology -> Object -> [Text] -> Either Text [SemanticGroupingDimension]
resolveDefaultGroupingDimensions ontology subjectObject rawDimensions =
  case rawDimensions of
    [] -> pure <$> groupingIdentityDimension subjectObject
    _ -> mapM (resolveGroupingDimensionValue ontology subjectObject) rawDimensions

resolveGroupingDimensionValue :: Ontology -> Object -> Text -> Either Text SemanticGroupingDimension
resolveGroupingDimensionValue ontology subjectObject rawDimension
  | trendDimensionMatchesSubject subjectObject rawDimension = groupingIdentityDimension subjectObject
  | otherwise =
      case resolveSubjectObject ontology rawDimension of
        Right dimensionObject -> groupingIdentityDimension dimensionObject
        Left _ ->
          case bestPublicDimensionMatch rawDimension subjectObject of
            Just dimensionNameValue ->
              Right
                SemanticGroupingDimension
                  { groupingDimensionObject = subjectObject
                  , groupingDimensionName = dimensionNameValue
                  }
            Nothing ->
              case bestOntologyGroupingDimensionMatch ontology rawDimension of
                Just dimensionNameValue ->
                  Right
                    SemanticGroupingDimension
                      { groupingDimensionObject = subjectObject
                      , groupingDimensionName = dimensionNameValue
                      }
                Nothing ->
                  Left
                    ( "Could not ground grouping dimension '"
                        <> rawDimension
                        <> "' to a public ontology dimension."
                    )

groupingIdentityDimension :: Object -> Either Text SemanticGroupingDimension
groupingIdentityDimension objectValue =
  maybe
    (Left ("No public identity dimension exists for grouping object '" <> objectName objectValue <> "'."))
    ( \dimensionNameValue ->
        Right
          SemanticGroupingDimension
            { groupingDimensionObject = objectValue
            , groupingDimensionName = dimensionNameValue
            }
    )
    (identityDimension objectValue)

bestOntologyGroupingDimensionMatch :: Ontology -> Text -> Maybe Text
bestOntologyGroupingDimensionMatch ontology rawDimension =
  case uniqueNames (map (attributeName . snd) rankedAttributes) of
    dimensionNameValue : _ -> Just dimensionNameValue
    [] -> Nothing
  where
    rawKey = normalizedKey rawDimension
    rankedAttributes =
      sortOn
        ( \(scoreValue, attributeValue) ->
            (Down scoreValue, attributeName attributeValue)
        )
        [ (groupingAttributeScore rawKey (attributeName attributeValue), attributeValue)
        | objectValue <- objects ontology
        , attributeValue <- OT.attributes objectValue
        , OT.visibility attributeValue == OT.Public
        , OT.kind attributeValue `elem` [OT.Dimension, OT.PrimaryKey]
        , groupingAttributeScore rawKey (attributeName attributeValue) > 0
        ]

groupingAttributeScore :: Text -> Text -> Int
groupingAttributeScore rawKey attributeNameValue
  | rawKey == attributeKey = 100
  | rawKey `T.isSuffixOf` attributeKey = 80
  | otherwise = 0
  where
    attributeKey = normalizedKey attributeNameValue

uniqueNames :: [Text] -> [Text]
uniqueNames names =
  case names of
    [] -> []
    nameValue : remaining ->
      nameValue : uniqueNames (filter (/= nameValue) remaining)

requireGroupingDimensionReachable :: Ontology -> Object -> Text -> Maybe ()
requireGroupingDimensionReachable ontology factObjectValue dimensionNameValue =
  case findAttribute factObjectValue dimensionNameValue of
    Just _ -> Just ()
    Nothing ->
      case
        [ ()
        | objectValue <- objects ontology
        , findAttribute objectValue dimensionNameValue /= Nothing
        , findPath ontology 2 (objectName factObjectValue) (objectName objectValue) /= Nothing
        ]
      of
        _ : _ -> Just ()
        [] -> Nothing
