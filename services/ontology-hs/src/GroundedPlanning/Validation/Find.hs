-- Purpose:
-- Validation rules for find/filter+join queries.

{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Find where

import Data.Text (Text)
import GroundedPlanning.Validation.Common
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (AttributeKind (PrimaryKey), AttributeVisibility (Public), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validateFindQuery :: Ontology -> FindQuerySpec -> Either Text ()
validateFindQuery ontology findQuery = do
  factObject <- requireObject ontology (findCoreFactObject findQuery)
  targetObjectValue <- requireObject ontology (findTargetObject findQuery)
  _ <- requirePath ontology (objectName factObject) (objectName targetObjectValue)
  validateFindDisplays targetObjectValue (findDisplayDimensions findQuery)
  validateFindPredicates ontology (objectName factObject) (findPredicates findQuery)
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

validateFindPredicates :: Ontology -> Text -> [FindPredicate] -> Either Text ()
validateFindPredicates ontology factObjectName predicateValues =
  case predicateValues of
    [] -> Left "Find queries require at least one grounded predicate."
    _ -> mapM_ (validateFindPredicate ontology factObjectName) predicateValues

validateFindPredicate :: Ontology -> Text -> FindPredicate -> Either Text ()
validateFindPredicate ontology factObjectName predicateValue = do
  predicateObject <- requireObject ontology (predicateTargetObject predicateValue)
  _ <- requirePath ontology factObjectName (predicateTargetObject predicateValue)
  attributeValue <-
    maybe
      (Left ("Find predicate attribute '" <> predicateAttribute predicateValue <> "' not found in ontology."))
      Right
      (findAttribute predicateObject (predicateAttribute predicateValue))
  if OT.kind attributeValue == PrimaryKey || OT.visibility attributeValue /= Public
    then Left "Find predicates must reference public non-primary ontology attributes."
    else pure ()

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
