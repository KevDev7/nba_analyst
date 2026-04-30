{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft.FilterGrounding
  ( groundDraftRowPredicate
  ) where

import Control.Applicative ((<|>))
import Data.List (nub, sortOn)
import Data.Ord (Down (Down))
import Data.Text (Text)
import qualified Data.Text as T
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (AttributeKind (Dimension, Measure), AttributeVisibility (Public), Object, Ontology (objects))
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Filters (draftFilterTextValue, seasonTypeFromFilter)
import QueryModel.SemanticDraft.Match (attributeName, identityDimension, objectName)
import QueryModel.SemanticDraft.MeasureMatch (measureAttributeScore)
import QueryModel.SemanticDraft.Normalize (normalizedKey, normalizedMeasureKey, subjectMatchKey)
import QueryModel.SemanticDraft.PredicateGrounding (combinePredicates, normalizePredicateOperator, numericFilterValue, textFilterValue)
import QueryModel.SemanticDraft.Types (DraftFilter (filterField, filterOp, filterValue), DraftPredicate (..))

groundDraftRowPredicate :: Ontology -> Object -> [DraftFilter] -> Maybe DraftPredicate -> Maybe (Maybe QI.Predicate)
groundDraftRowPredicate ontology factObjectValue draftFilters maybeDraftPredicate = do
  -- Canonicalize simple draft filters into the shared row-predicate tree.
  filterPredicates <- mapM (groundDraftFilterPredicate ontology factObjectValue) (rowPredicateCandidates draftFilters)
  directPredicateValues <-
    case maybeDraftPredicate of
      Nothing -> Just []
      Just draftPredicate -> pure <$> groundDraftPredicate ontology factObjectValue draftPredicate
  Just (combinePredicates (filterPredicates <> directPredicateValues))

groundDraftPredicate :: Ontology -> Object -> DraftPredicate -> Maybe QI.Predicate
groundDraftPredicate ontology factObjectValue draftPredicate =
  case draftPredicate of
    DraftPredicateLeaf {draftPredicateField = rawField, draftPredicateOp = maybeRawOp, draftPredicateValue = rawValue} -> do
      opValue <- normalizePredicateOperator maybeRawOp
      (targetObjectValue, attributeValue) <- resolveRowPredicateAttribute ontology factObjectValue rawField
      pure
        ( QI.PredicateLeaf
            QI.PredicateField
              { QI.predicateFieldTargetObject = objectName targetObjectValue
              , QI.predicateFieldAttribute = attributeName attributeValue
              , QI.predicateLocation = QI.PredicateRowField
              }
            opValue
            rawValue
        )
    DraftPredicateAnd predicateValues ->
      QI.PredicateAnd <$> mapM (groundDraftPredicate ontology factObjectValue) predicateValues
    DraftPredicateOr predicateValues ->
      QI.PredicateOr <$> mapM (groundDraftPredicate ontology factObjectValue) predicateValues
    DraftPredicateNot predicateValue ->
      QI.PredicateNot <$> groundDraftPredicate ontology factObjectValue predicateValue

rowPredicateCandidates :: [DraftFilter] -> [DraftFilter]
rowPredicateCandidates =
  filter (not . isTimeOrSeasonFilter)

isTimeOrSeasonFilter :: DraftFilter -> Bool
isTimeOrSeasonFilter draftFilter =
  seasonTypeFromFilter draftFilter /= Nothing
    || maybe False isTimeOrSeasonField (filterField draftFilter)
    || maybe False isSeasonValue (draftFilterTextValue draftFilter)

isTimeOrSeasonField :: Text -> Bool
isTimeOrSeasonField rawField =
  normalizedKey rawField
    `elem` [ "season"
           , "seasonyear"
           , "seasons"
           , "year"
           , "seasontype"
           , "gametype"
           , "lastngames"
           , "pastyear"
           , "timewindow"
           ]

isSeasonValue :: Text -> Bool
isSeasonValue rawValue =
  "season" `T.isInfixOf` normalizedKey rawValue

groundDraftFilterPredicate :: Ontology -> Object -> DraftFilter -> Maybe QI.Predicate
groundDraftFilterPredicate ontology factObjectValue draftFilter = do
  rawField <- filterField draftFilter
  rawValue <- filterValue draftFilter
  opValue <- normalizePredicateOperator (filterOp draftFilter)
  (targetObjectValue, attributeValue) <- resolveRowPredicateFilterAttribute ontology factObjectValue rawField opValue rawValue
  groundedValue <- rowPredicateValueForAttribute rawField attributeValue opValue rawValue
  pure
    ( QI.PredicateLeaf
        QI.PredicateField
          { QI.predicateFieldTargetObject = objectName targetObjectValue
          , QI.predicateFieldAttribute = attributeName attributeValue
          , QI.predicateLocation = QI.PredicateRowField
          }
        opValue
        (QI.PredicateScalar groundedValue)
    )

rowPredicateValueForAttribute :: Text -> OT.Attribute -> QI.PredicateOperator -> QI.FilterValue -> Maybe QI.FilterValue
rowPredicateValueForAttribute rawField attributeValue opValue rawValue =
  case OT.kind attributeValue of
    Dimension -> do
      _ <- requireEqualityOp opValue
      textValue <- textFilterValue rawValue
      pure (QI.FilterText textValue)
    Measure -> do
      _ <- rejectAggregatePredicateWording rawField
      numericFilterValue rawValue
    OT.PrimaryKey -> Nothing

requireEqualityOp :: QI.PredicateOperator -> Maybe ()
requireEqualityOp opValue =
  case opValue of
    QI.PredicateEquals -> Just ()
    _ -> Nothing

rejectAggregatePredicateWording :: Text -> Maybe ()
rejectAggregatePredicateWording rawField =
  if any (`T.isInfixOf` fieldKey) aggregateKeys
    then Nothing
    else Just ()
  where
    fieldKey = normalizedMeasureKey rawField
    aggregateKeys =
      [ "average"
      , "avg"
      , "pergame"
      , "total"
      , "sum"
      ]

resolveRowPredicateFilterAttribute :: Ontology -> Object -> Text -> QI.PredicateOperator -> QI.FilterValue -> Maybe (Object, OT.Attribute)
resolveRowPredicateFilterAttribute ontology factObjectValue rawField opValue rawValue =
  objectIdentityAttributeMatch ontology factObjectValue rawField opValue rawValue
    <|> bestReachablePublicAttributeMatch ontology factObjectValue rawField opValue rawValue

resolveRowPredicateAttribute :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
resolveRowPredicateAttribute ontology factObjectValue rawField =
  rowPredicateObjectIdentityAttributeMatch ontology factObjectValue rawField
    <|> bestReachablePublicPredicateAttributeMatch ontology factObjectValue rawField

rowPredicateObjectIdentityAttributeMatch :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
rowPredicateObjectIdentityAttributeMatch ontology factObjectValue rawField =
  case
    [ (objectValue, attributeValue)
    | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
    , subjectMatchKey rawField == subjectMatchKey (objectName objectValue)
    , Just identityName <- [identityDimension objectValue]
    , Just attributeValue <- [findAttribute objectValue identityName]
    , OT.visibility attributeValue == Public
    , OT.kind attributeValue == Dimension
    ]
    of
    matchValue : _ -> Just matchValue
    [] -> Nothing

bestReachablePublicPredicateAttributeMatch :: Ontology -> Object -> Text -> Maybe (Object, OT.Attribute)
bestReachablePublicPredicateAttributeMatch ontology factObjectValue rawField =
  case sortOn rowPredicateAttributeRank matches of
    matchValue : _ -> Just matchValue
    [] -> Nothing
  where
    matches =
      [ (objectValue, attributeValue)
      | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
      , attributeValue <- OT.attributes objectValue
      , OT.visibility attributeValue == Public
      , OT.kind attributeValue `elem` [Dimension, Measure]
      , rowPredicateAttributeScore rawField objectValue attributeValue > 0
      ]
    rowPredicateAttributeRank (objectValue, attributeValue) =
      ( Down (rowPredicateAttributeScore rawField objectValue attributeValue)
      , if objectName objectValue == objectName factObjectValue then (0 :: Int) else 1
      , objectName objectValue
      , attributeName attributeValue
      )

objectIdentityAttributeMatch :: Ontology -> Object -> Text -> QI.PredicateOperator -> QI.FilterValue -> Maybe (Object, OT.Attribute)
objectIdentityAttributeMatch ontology factObjectValue rawField opValue rawValue = do
  _ <- requireEqualityOp opValue
  _ <- textFilterValue rawValue
  case
    [ (objectValue, attributeValue)
    | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
    , subjectMatchKey rawField == subjectMatchKey (objectName objectValue)
    , Just identityName <- [identityDimension objectValue]
    , Just attributeValue <- [findAttribute objectValue identityName]
    , isPublicDimension attributeValue
    ]
    of
    matchValue : _ -> Just matchValue
    [] -> Nothing

bestReachablePublicAttributeMatch :: Ontology -> Object -> Text -> QI.PredicateOperator -> QI.FilterValue -> Maybe (Object, OT.Attribute)
bestReachablePublicAttributeMatch ontology factObjectValue rawField opValue rawValue =
  case sortOn rowPredicateAttributeRank matches of
    matchValue : _ -> Just matchValue
    [] -> Nothing
  where
    matches =
      [ (objectValue, attributeValue)
      | objectValue <- factObjectValue : reachableObjects ontology factObjectValue
      , attributeValue <- OT.attributes objectValue
      , isSupportedRowPredicateAttribute opValue rawValue attributeValue
      , rowPredicateAttributeScore rawField objectValue attributeValue > 0
      ]
    rowPredicateAttributeRank (objectValue, attributeValue) =
      ( Down (rowPredicateAttributeScore rawField objectValue attributeValue)
      , if objectName objectValue == objectName factObjectValue then (0 :: Int) else 1
      , objectName objectValue
      , attributeName attributeValue
      )

rowPredicateAttributeScore :: Text -> Object -> OT.Attribute -> Int
rowPredicateAttributeScore rawField objectValue attributeValue
  | rawKey == attributeKey = 100
  | rawKey == T.replace objectKey "" attributeKey = 95
  | rawKey `elem` aliasKeys = 90
  | rawKey `T.isSuffixOf` attributeKey = 80
  | measureAttributeScore rawField objectValue attributeValue > 0 = measureAttributeScore rawField objectValue attributeValue
  | otherwise = 0
  where
    rawKey = normalizedMeasureKey rawField
    objectKey = normalizedKey (objectName objectValue)
    attributeKey = normalizedMeasureKey (attributeName attributeValue)
    aliasKeys =
      nub
        [ T.replace "team" "" attributeKey
        , T.replace "player" "" attributeKey
        , T.replace "opponent" "" attributeKey
        , T.replace "played" "" attributeKey
        ]

reachableObjects :: Ontology -> Object -> [Object]
reachableObjects ontology factObjectValue =
  [ candidateObject
  | candidateObject <- objects ontology
  , objectName candidateObject /= objectName factObjectValue
  , findPath ontology 2 (objectName factObjectValue) (objectName candidateObject) /= Nothing
  ]

isPublicDimension :: OT.Attribute -> Bool
isPublicDimension attributeValue =
  OT.kind attributeValue == Dimension && OT.visibility attributeValue == Public

isPublicMeasure :: OT.Attribute -> Bool
isPublicMeasure attributeValue =
  OT.kind attributeValue == Measure && OT.visibility attributeValue == Public

isSupportedRowPredicateAttribute :: QI.PredicateOperator -> QI.FilterValue -> OT.Attribute -> Bool
isSupportedRowPredicateAttribute opValue rawValue attributeValue
  | isPublicDimension attributeValue =
      opValue == QI.PredicateEquals && textFilterValue rawValue /= Nothing
  | isPublicMeasure attributeValue =
      numericFilterValue rawValue /= Nothing
  | otherwise = False
