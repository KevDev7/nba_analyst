-- Purpose:
-- Validation rules for find/filter+join queries.

{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Find where

import Data.Text (Text)
import GroundedPlanning.Validation.Common
import GroundedPlanning.Validation.Common.PredicateRules
import OntologyLayer.Graph (DiscoveredPath, findAllPathsFrom, findAttribute, findObject, findPath, findPathByLastLinkName, findPathsFrom)
import qualified OntologyLayer.Graph as OG
import OntologyLayer.Types (AttributeKind (Dimension, Measure, PrimaryKey), AttributeVisibility (Public), Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR

validateFindQuery :: Ontology -> FindQuerySpec -> Either Text ()
validateFindQuery ontology findQuery = do
  factObject <- requireObject ontology (findCoreFactObject findQuery)
  targetObjectValue <- requireObject ontology (findTargetObject findQuery)
  _ <- requirePath ontology (objectName factObject) (objectName targetObjectValue)
  validateFindDisplays ontology factObject targetObjectValue (findDisplayDimensions findQuery)
  validateFindOrders ontology factObject targetObjectValue (findOrders findQuery)
  validateFindPredicateShape ontology (objectName factObject) (findPredicateTree findQuery) (findFilters findQuery)
  validateFindFilters factObject (findFilters findQuery)
  validateFindLimit (findLimit findQuery)

validateFindDisplays :: Ontology -> OT.Object -> OT.Object -> [FindDisplaySpec] -> Either Text ()
validateFindDisplays ontology factObjectValue targetObjectValue displayValues =
  case displayValues of
    [] -> Left "Find queries require at least one display dimension."
    _ -> mapM_ (validateFindDisplay ontology factObjectValue targetObjectValue) displayValues

validateFindDisplay :: Ontology -> OT.Object -> OT.Object -> FindDisplaySpec -> Either Text ()
validateFindDisplay ontology factObjectValue targetObjectValue displaySpec = do
  attributeValue <-
    maybe
      (Left ("Find display attribute '" <> findDisplayAttribute displaySpec <> "' not found on the selected fact object, target object, or reachable ontology links."))
      Right
      (findFindDisplayAttribute ontology factObjectValue targetObjectValue displaySpec)
  if OT.kind attributeValue == PrimaryKey || OT.visibility attributeValue /= Public
    then Left "Find display attributes must be public non-primary attributes."
    else pure ()

validateFindOrders :: Ontology -> OT.Object -> OT.Object -> [FindOrderSpec] -> Either Text ()
validateFindOrders ontology factObjectValue targetObjectValue orderValues =
  mapM_ (validateFindOrder ontology factObjectValue targetObjectValue) orderValues

validateFindOrder :: Ontology -> OT.Object -> OT.Object -> FindOrderSpec -> Either Text ()
validateFindOrder ontology factObjectValue targetObjectValue orderSpec = do
  attributeValue <-
    maybe
      (Left ("Find order attribute '" <> findDisplayAttribute (findOrderField orderSpec) <> "' not found on the selected fact object, target object, or reachable ontology links."))
      Right
      (findFindDisplayAttribute ontology factObjectValue targetObjectValue (findOrderField orderSpec))
  if OT.kind attributeValue == PrimaryKey || OT.visibility attributeValue /= Public
    then Left "Find order attributes must be public non-primary attributes."
    else pure ()

findFindDisplayAttribute :: Ontology -> OT.Object -> OT.Object -> FindDisplaySpec -> Maybe OT.Attribute
findFindDisplayAttribute ontology factObjectValue targetObjectValue displaySpec =
  case findFindDisplayAttributes ontology factObjectValue targetObjectValue displaySpec of
    attributeValue : _ -> Just attributeValue
    [] -> Nothing

findFindDisplayAttributes :: Ontology -> OT.Object -> OT.Object -> FindDisplaySpec -> [OT.Attribute]
findFindDisplayAttributes ontology factObjectValue targetObjectValue displaySpec =
  case findDisplayLinkRole displaySpec of
    Just linkRoleValue -> roleLinkedAttributes linkRoleValue
    Nothing -> targetAttributes <> factAttributes <> linkedAttributes
  where
    displayName = findDisplayAttribute displaySpec
    targetAttributes =
      [ attributeValue
      | Just attributeValue <- [findAttribute targetObjectValue displayName]
      , isPublicFindDisplayAttribute attributeValue
      , findDisplayTargetObject displaySpec `elem` [Nothing, Just (objectName targetObjectValue)]
      ]
    factAttributes =
      [ attributeValue
      | findPath ontology 2 (objectName factObjectValue) (objectName factObjectValue) /= Nothing
      , Just attributeValue <- [findAttribute factObjectValue displayName]
      , isPublicFindDisplayAttribute attributeValue
      , findDisplayTargetObject displaySpec `elem` [Nothing, Just (objectName factObjectValue)]
      ]
    linkedAttributes =
      [ attributeValue
      | discoveredPath <- findPathsFrom ontology 2 (objectName factObjectValue)
      , OG.targetObjectName discoveredPath /= objectName targetObjectValue
      , Just linkedObject <- [findObject ontology (OG.targetObjectName discoveredPath)]
      , Just attributeValue <- [findAttribute linkedObject displayName]
      , isPublicFindDisplayAttribute attributeValue
      , findDisplayTargetObject displaySpec `elem` [Nothing, Just (objectName linkedObject)]
      ]
    roleLinkedAttributes linkRoleValue =
      [ attributeValue
      | discoveredPath <- findAllPathsFrom ontology 2 (objectName factObjectValue)
      , lastLinkName discoveredPath == linkRoleValue
      , Just linkedObject <- [findObject ontology (OG.targetObjectName discoveredPath)]
      , findDisplayTargetObject displaySpec `elem` [Nothing, Just (objectName linkedObject)]
      , Just attributeValue <- [findAttribute linkedObject displayName]
      , isPublicFindDisplayAttribute attributeValue
      ]

lastLinkName :: DiscoveredPath -> Text
lastLinkName pathValue =
  case reverse (OG.steps pathValue) of
    stepValue : _ -> OG.linkName stepValue
    [] -> ""

isPublicFindDisplayAttribute :: OT.Attribute -> Bool
isPublicFindDisplayAttribute attributeValue =
  OT.kind attributeValue `elem` [Dimension, Measure]
    && OT.visibility attributeValue == Public

validateFindPredicateShape :: Ontology -> Text -> Maybe Predicate -> [Filter] -> Either Text ()
validateFindPredicateShape ontology factObjectName maybePredicateTree filterValues =
  case (maybePredicateTree, filterValues) of
    (Nothing, []) -> Left "Find queries require at least one grounded predicate or bounded time filter."
    _ -> mapM_ (validateFindPredicateTree ontology factObjectName) maybePredicateTree

validateFindPredicateTree :: Ontology -> Text -> Predicate -> Either Text ()
validateFindPredicateTree ontology factObjectName predicateTree =
  validatePredicateTree "Find" (validateFindPredicateLeaf ontology factObjectName) predicateTree

validateFindPredicateLeaf :: Ontology -> Text -> PredicateField -> PredicateOperator -> PredicateValue -> Either Text ()
validateFindPredicateLeaf ontology factObjectName fieldValue operatorValue predicateValue = do
  validatePredicateLocation "Find" PredicateRowField fieldValue
  predicateObject <- requireObject ontology (predicateFieldTargetObject fieldValue)
  _ <-
    case predicateFieldLinkRole fieldValue of
      Just linkRoleValue ->
        maybe
          (Left ("Find predicate path through link role '" <> linkRoleValue <> "' not found in ontology."))
          Right
          (findPathByLastLinkName ontology 2 factObjectName (predicateFieldTargetObject fieldValue) linkRoleValue)
      Nothing -> requirePath ontology factObjectName (predicateFieldTargetObject fieldValue)
  attributeValue <-
    maybe
      (Left ("Find predicate attribute '" <> predicateFieldAttribute fieldValue <> "' not found in ontology."))
      Right
      (findAttribute predicateObject (predicateFieldAttribute fieldValue))
  if OT.kind attributeValue == PrimaryKey || OT.visibility attributeValue /= Public
    then Left "Find predicate trees must reference public non-primary ontology attributes."
    else
      validateRowLikePredicateOperatorValue
        "Find predicate tree operator/value is not valid for the resolved ontology attribute."
        attributeValue
        operatorValue
        predicateValue

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
