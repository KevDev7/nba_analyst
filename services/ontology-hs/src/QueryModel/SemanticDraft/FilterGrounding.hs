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
import qualified Data.Text.Read as TR
import OntologyLayer.Graph (findAttribute, findPath)
import OntologyLayer.Types (AttributeKind (Dimension, Measure), AttributeVisibility (Public), Object, Ontology (objects))
import qualified OntologyLayer.Types as OT
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Filters (draftFilterTextValue, seasonTypeFromFilter)
import QueryModel.SemanticDraft.Match (attributeName, identityDimension, objectName)
import QueryModel.SemanticDraft.MeasureMatch (measureAttributeScore)
import QueryModel.SemanticDraft.Normalize (normalizedKey, normalizedMeasureKey, subjectMatchKey)
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

combinePredicates :: [QI.Predicate] -> Maybe QI.Predicate
combinePredicates predicateValues =
  case predicateValues of
    [] -> Nothing
    [predicateValue] -> Just predicateValue
    _ -> Just (QI.PredicateAnd predicateValues)

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

normalizePredicateOperator :: Maybe Text -> Maybe QI.PredicateOperator
normalizePredicateOperator maybeRawOp =
  case T.strip <$> maybeRawOp of
    Just "=" -> Just QI.PredicateEquals
    Just "!=" -> Just QI.PredicateNotEquals
    Just "<>" -> Just QI.PredicateNotEquals
    Just ">" -> Just QI.PredicateGreaterThan
    Just ">=" -> Just QI.PredicateGreaterThanOrEqual
    Just "<" -> Just QI.PredicateLessThan
    Just "<=" -> Just QI.PredicateLessThanOrEqual
    _ ->
      case normalizedKey <$> maybeRawOp of
        Nothing -> Just QI.PredicateEquals
        Just "" -> Just QI.PredicateEquals
        Just "eq" -> Just QI.PredicateEquals
        Just "equals" -> Just QI.PredicateEquals
        Just "is" -> Just QI.PredicateEquals
        Just "notequals" -> Just QI.PredicateNotEquals
        Just "not" -> Just QI.PredicateNotEquals
        Just "neq" -> Just QI.PredicateNotEquals
        Just "over" -> Just QI.PredicateGreaterThan
        Just "above" -> Just QI.PredicateGreaterThan
        Just "greaterthan" -> Just QI.PredicateGreaterThan
        Just "gt" -> Just QI.PredicateGreaterThan
        Just "morethan" -> Just QI.PredicateGreaterThan
        Just "atleast" -> Just QI.PredicateGreaterThanOrEqual
        Just "gte" -> Just QI.PredicateGreaterThanOrEqual
        Just "under" -> Just QI.PredicateLessThan
        Just "below" -> Just QI.PredicateLessThan
        Just "lessthan" -> Just QI.PredicateLessThan
        Just "lt" -> Just QI.PredicateLessThan
        Just "atmost" -> Just QI.PredicateLessThanOrEqual
        Just "lte" -> Just QI.PredicateLessThanOrEqual
        Just "in" -> Just QI.PredicateIn
        Just "notin" -> Just QI.PredicateNotIn
        Just "between" -> Just QI.PredicateBetween
        Just "contains" -> Just QI.PredicateContains
        _ -> Nothing

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

textFilterValue :: QI.FilterValue -> Maybe Text
textFilterValue rawValue =
  case rawValue of
    QI.FilterText textValue
      | T.strip textValue /= "" -> Just textValue
    _ -> Nothing

numericFilterValue :: QI.FilterValue -> Maybe QI.FilterValue
numericFilterValue rawValue =
  case rawValue of
    QI.FilterInt _ -> Just rawValue
    QI.FilterDouble _ -> Just rawValue
    QI.FilterText textValue -> parseNumericText textValue

parseNumericText :: Text -> Maybe QI.FilterValue
parseNumericText rawValue =
  case TR.signed TR.decimal strippedValue of
    Right (intValue, remaining) | T.strip remaining == "" -> Just (QI.FilterInt intValue)
    _ ->
      case TR.signed TR.double doubleReadyValue of
        Right (doubleValue, remaining) | T.strip remaining == "" -> Just (QI.FilterDouble doubleValue)
        _ -> Nothing
  where
    strippedValue = T.strip rawValue
    doubleReadyValue =
      case T.uncons strippedValue of
        Just ('.', _) -> "0" <> strippedValue
        Just ('-', rest) ->
          case T.uncons rest of
            Just ('.', _) -> "-0" <> rest
            _ -> strippedValue
        _ -> strippedValue

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
