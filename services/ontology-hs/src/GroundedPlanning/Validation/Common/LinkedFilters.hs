{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Validation.Common.LinkedFilters
  ( recentLinkedFilterFactSurfaceMessage
  , requirePublicLinkedFilterDimension
  , seasonLinkedFilterFactSurfaceMessage
  , validateLinkedFilterFactSurface
  , validateLinkedFilters
  , validateOrdinaryLinkedFilters
  , validateSeasonLinkedFilterFactSurface
  ) where

import Data.Text (Text)
import OntologyLayer.Graph (findAttribute)
import OntologyLayer.Types (AttributeKind (Dimension), Object, Ontology)
import qualified OntologyLayer.Types as OT
import QueryModel.IR
import GroundedPlanning.Validation.Common.Ontology
import GroundedPlanning.Validation.Common.Types

validateLinkedFilters :: Ontology -> Text -> [LinkedFilter] -> Either Text ()
validateLinkedFilters ontology factObjectName linkedFilterValues =
  mapM_ validateLinkedFilter linkedFilterValues
  where
    validateLinkedFilter linkedFilterValue = do
      _ <- requirePath ontology factObjectName (targetObject linkedFilterValue)
      targetObjectValue <- requireObject ontology (targetObject linkedFilterValue)
      requirePublicLinkedFilterDimension targetObjectValue (attribute linkedFilterValue)

validateOrdinaryLinkedFilters :: Ontology -> OrdinaryLinkedFilterQueryKind -> OrdinaryMetricFilterFamily -> Text -> [LinkedFilter] -> Either Text ()
validateOrdinaryLinkedFilters ontology queryKind filterFamily factObjectName linkedFilterValues = do
  validateLinkedFilters ontology factObjectName linkedFilterValues
  case linkedFilterValues of
    [] -> pure ()
    _ -> validateLinkedFilterFactSurface ontology queryKind filterFamily factObjectName

validateLinkedFilterFactSurface :: Ontology -> OrdinaryLinkedFilterQueryKind -> OrdinaryMetricFilterFamily -> Text -> Either Text ()
validateLinkedFilterFactSurface ontology queryKind filterFamily factObjectName = do
  factObject <- requireObject ontology factObjectName
  case filterFamily of
    RecentMetricWindow -> requireFactAttribute factObject "game_date" (recentLinkedFilterFactSurfaceMessage queryKind)
    SeasonMetricWindow -> do
      requireFactAttribute factObject "season_year" (seasonLinkedFilterFactSurfaceMessage queryKind)
      requireFactAttribute factObject "season_type" (seasonLinkedFilterFactSurfaceMessage queryKind)
      validateSeasonLinkedFilterFactSurface queryKind factObject

recentLinkedFilterFactSurfaceMessage :: OrdinaryLinkedFilterQueryKind -> Text
recentLinkedFilterFactSurfaceMessage queryKind =
  case queryKind of
    MetricLinkedFilterQuery ->
      "Recent metric queries with linked filters require a fact surface that exposes game_date."
    ObjectLinkedFilterQuery ->
      "Recent object queries with linked filters require a fact surface that exposes game_date."

seasonLinkedFilterFactSurfaceMessage :: OrdinaryLinkedFilterQueryKind -> Text
seasonLinkedFilterFactSurfaceMessage queryKind =
  case queryKind of
    MetricLinkedFilterQuery ->
      "Season-scoped metric queries with linked filters require a fact surface that exposes season_year and season_type."
    ObjectLinkedFilterQuery ->
      "Season-scoped object queries with linked filters require a fact surface that exposes season_year and season_type."

requirePublicLinkedFilterDimension :: Object -> Text -> Either Text ()
requirePublicLinkedFilterDimension object attributeName = do
  attribute <-
    maybe
      (Left ("Linked filters support public dimension attributes on reachable ontology objects only."))
      Right
      (findAttribute object attributeName)
  if OT.kind attribute /= Dimension || OT.visibility attribute /= OT.Public
    then Left "Linked filters support public dimension attributes on reachable ontology objects only."
    else pure ()

validateSeasonLinkedFilterFactSurface :: OrdinaryLinkedFilterQueryKind -> Object -> Either Text ()
validateSeasonLinkedFilterFactSurface queryKind factObject =
  case queryKind of
    MetricLinkedFilterQuery ->
      if hasAttribute factObject "game_date"
        then Left "Season-scoped metric queries with linked filters require a season-level fact surface rather than per-game rows."
        else pure ()
    ObjectLinkedFilterQuery -> pure ()
