-- Purpose:
-- Validation rules for find/filter+join queries.

{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Find where

import Data.Text (Text)
import GroundedPlanning.Validation.Common
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (AttributeKind (Dimension, Measure, PrimaryKey), AttributeVisibility (Public), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validateFindQuery :: Ontology -> FindQuerySpec -> Either Text ()
validateFindQuery ontology findQuery = do
  factObject <- requireObject ontology (findCoreFactObject findQuery)
  targetObjectValue <- requireObject ontology (findTargetObject findQuery)
  _ <- requirePath ontology (objectName factObject) (objectName targetObjectValue)
  validateFindDisplays targetObjectValue (findDisplayDimensions findQuery)
  validateFindPredicateShape ontology (objectName factObject) (findPredicateTree findQuery) (findFilters findQuery)
  validateFindFilters factObject (findFilters findQuery)
  validateFindLimit (findLimit findQuery)

validateFindDisplays :: OT.Object -> [DimensionName] -> Either Text ()
validateFindDisplays targetObjectValue displayValues =
  case displayValues of
    [] -> Left "Find queries require at least one display dimension."
    _ -> mapM_ (validateFindDisplay targetObjectValue) displayValues

validateFindDisplay :: OT.Object -> DimensionName -> Either Text ()
validateFindDisplay targetObjectValue displayName = do
  attributeValue <-
    maybe
      (Left ("Find display dimension '" <> displayName <> "' not found on target object."))
      Right
      (findAttribute targetObjectValue displayName)
  if OT.kind attributeValue == PrimaryKey || OT.visibility attributeValue /= Public
    then Left "Find display dimensions must be public non-primary attributes."
    else pure ()

validateFindPredicateShape :: Ontology -> Text -> Maybe Predicate -> [Filter] -> Either Text ()
validateFindPredicateShape ontology factObjectName maybePredicateTree filterValues =
  case (maybePredicateTree, filterValues) of
    (Nothing, []) -> Left "Find queries require at least one grounded predicate or bounded time filter."
    _ -> mapM_ (validateFindPredicateTree ontology factObjectName) maybePredicateTree

validateFindPredicateTree :: Ontology -> Text -> Predicate -> Either Text ()
validateFindPredicateTree ontology factObjectName predicateTree =
  case predicateTree of
    PredicateLeaf fieldValue operatorValue predicateValue -> validateFindPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue
    PredicateAnd predicateValues -> validatePredicateChildren "AND" ontology factObjectName predicateValues
    PredicateOr predicateValues -> validatePredicateChildren "OR" ontology factObjectName predicateValues
    PredicateNot predicateValue -> validateFindPredicateTree ontology factObjectName predicateValue

validatePredicateChildren :: Text -> Ontology -> Text -> [Predicate] -> Either Text ()
validatePredicateChildren label ontology factObjectName predicateValues =
  case predicateValues of
    [] -> Left ("Find " <> label <> " predicate requires at least one child predicate.")
    _ -> mapM_ (validateFindPredicateTree ontology factObjectName) predicateValues

validateFindPredicateLeaf :: Ontology -> Text -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ()
validateFindPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue = do
  case predicateLocation fieldValue of
    PredicateRowField -> pure ()
    PredicateResultField -> Left "Find predicate trees only support row-level predicate fields."
  predicateObject <- requireObject ontology (predicateFieldTargetObject fieldValue)
  _ <- requirePath ontology factObjectName (predicateFieldTargetObject fieldValue)
  attributeValue <-
    maybe
      (Left ("Find predicate attribute '" <> predicateFieldAttribute fieldValue <> "' not found in ontology."))
      Right
      (findAttribute predicateObject (predicateFieldAttribute fieldValue))
  if OT.kind attributeValue == PrimaryKey || OT.visibility attributeValue /= Public
    then Left "Find predicate trees must reference public non-primary ontology attributes."
    else validateFindPredicateOperatorValue attributeValue operatorValue predicateValue

validateFindPredicateOperatorValue :: OT.Attribute -> PredicateOperator -> PredicateValue -> Either Text ()
validateFindPredicateOperatorValue attributeValue operatorValue predicateValue =
  case (OT.kind attributeValue, operatorValue, predicateValue) of
    (Dimension, PredicateEquals, PredicateScalar (FilterText textValue))
      | textValue /= "" -> pure ()
    (Dimension, PredicateNotEquals, PredicateScalar (FilterText textValue))
      | textValue /= "" -> pure ()
    (Dimension, PredicateIn, PredicateList values)
      | all isNonEmptyText values && not (null values) -> pure ()
    (Dimension, PredicateNotIn, PredicateList values)
      | all isNonEmptyText values && not (null values) -> pure ()
    (Dimension, PredicateContains, PredicateScalar (FilterText textValue))
      | textValue /= "" -> pure ()
    (Measure, PredicateEquals, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateNotEquals, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateGreaterThan, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateGreaterThanOrEqual, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateLessThan, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateLessThanOrEqual, PredicateScalar value)
      | isNumericFilterValue value -> pure ()
    (Measure, PredicateIn, PredicateList values)
      | all isNumericFilterValue values && not (null values) -> pure ()
    (Measure, PredicateNotIn, PredicateList values)
      | all isNumericFilterValue values && not (null values) -> pure ()
    (Measure, PredicateBetween, PredicateRange lowerValue upperValue)
      | isNumericFilterValue lowerValue && isNumericFilterValue upperValue -> pure ()
    _ -> Left "Find predicate tree operator/value is not valid for the resolved ontology attribute."

isNonEmptyText :: FilterValue -> Bool
isNonEmptyText filterValue =
  case filterValue of
    FilterText textValue -> textValue /= ""
    _ -> False

isNumericFilterValue :: FilterValue -> Bool
isNumericFilterValue filterValue =
  case filterValue of
    FilterInt _ -> True
    FilterDouble _ -> True
    FilterText _ -> False

validateFindFilters :: OT.Object -> [Filter] -> Either Text ()
validateFindFilters factObject filterValues =
  mapM_ validateFindFilter filterValues
  where
    validateFindFilter filterValue =
      case filterKindText filterValue of
        "last_n_games" -> do
          requireFactAttribute factObject "game_date" "Find last-N-games filters require an ontology-backed game_date attribute."
          case filterIntValue filterValue of
            Just gamesValue | gamesValue > 0 -> pure ()
            _ -> Left "Find last-N-games filters require a positive integer value."
        "past_year" -> do
          requireFactAttribute factObject "game_date" "Find past-year filters require an ontology-backed game_date attribute."
          pure ()
        "last_n_days" -> do
          requireFactAttribute factObject "game_date" "Find last-N-days filters require an ontology-backed game_date attribute."
          case filterIntValue filterValue of
            Just daysValue | daysValue > 0 -> pure ()
            _ -> Left "Find last-N-days filters require a positive integer value."
        "date_from" -> do
          requireFactAttribute factObject "game_date" "Find date-range filters require an ontology-backed game_date attribute."
          case filterTextValue filterValue of
            Just _ -> pure ()
            Nothing -> Left "Find date-from filters require a text value."
        "date_to" -> do
          requireFactAttribute factObject "game_date" "Find date-range filters require an ontology-backed game_date attribute."
          case filterTextValue filterValue of
            Just _ -> pure ()
            Nothing -> Left "Find date-to filters require a text value."
        "exact_season" -> do
          requireFactAttribute factObject "season_year" "Find season filters require an ontology-backed season_year attribute."
          case filterTextValue filterValue of
            Just _ -> pure ()
            Nothing -> Left "Find exact-season filters require a text value."
        "season_type" -> do
          requireFactAttribute factObject "season_type" "Find season-type filters require an ontology-backed season_type attribute."
          case filterTextValue filterValue of
            Just _ -> pure ()
            Nothing -> Left "Find season-type filters require a text value."
        _ -> Left ("Unsupported find filter kind '" <> filterKindText filterValue <> "'.")

validateFindLimit :: Maybe Int -> Either Text ()
validateFindLimit maybeLimit =
  case maybeLimit of
    Nothing -> pure ()
    Just limitValue
      | limitValue > 0 -> pure ()
      | otherwise -> Left "Find query limit must be positive when provided."
