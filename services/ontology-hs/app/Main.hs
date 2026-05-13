-- Purpose:
-- Entry point for the Haskell semantic core.
--
-- Uses:
-- - ontology loading from OntologyLayer.Load
-- - query-model construction from QueryModel modules
-- - grounded planning from GroundedPlanning modules
--
-- Produces:
-- - a JSON planning payload containing IR and execution plan
--
-- Next:
-- - apps/cli/main.py

{-# LANGUAGE DeriveGeneric #-}
{-# LANGUAGE DuplicateRecordFields #-}
{-# LANGUAGE OverloadedStrings #-}

module Main where

import Data.Aeson (ToJSON, encode, eitherDecodeStrict')
import qualified Data.Aeson as Aeson
import qualified Data.ByteString.Lazy.Char8 as BL8
import Data.Text (Text, pack)
import qualified Data.Text as Text
import Data.Text.Encoding (encodeUtf8)
import GHC.Generics (Generic)
import GroundedPlanning.Compile (compileExecutionPlan)
import GroundedPlanning.Plan (ExecutionPlan)
import GroundedPlanning.Resolve (ResolvedQuery, resolveQuery)
import GroundedPlanning.Validation (validateQuery)
import OntologyLayer.Load (loadOntologyEither)
import OntologyLayer.Types
  ( Attribute (..)
  , AttributeKind (..)
  , AttributeVisibility (..)
  , MetricDef (..)
  , Object (..)
  , Ontology (..)
  )
import QueryModel.IR (Query (FindQuery, MetricQuery, ObjectQuery))
import QueryModel.SemanticDraft (SemanticDraft, semanticDraftToQuery)
import System.Environment (getArgs)
import System.Exit (die, exitFailure)

data PlannerOutput = PlannerOutput
  -- Successful response shape sent back to Python.
  -- It includes each major planner artifact so --debug can show the pipeline.
  { query_type :: Text
  , query :: Query
  , resolved_query :: ResolvedQuery
  , execution_plan :: ExecutionPlan
  }
  deriving (Show, Generic)

instance ToJSON PlannerOutput

data PlannerError = PlannerError
  -- Error response shape sent back to Python when any Haskell stage fails.
  { stage :: Text
  , message :: Text
  }
  deriving (Show, Generic)

instance ToJSON PlannerError

data OntologyValidationResponse = OntologyValidationResponse
  { status :: Text
  }
  deriving (Show, Generic)

instance ToJSON OntologyValidationResponse

main :: IO ()
main = do
  -- Look at the command Python sent and route to the matching Haskell mode.
  args <- getArgs
  case args of
    ["validate-ontology-json", "--ontology", ontologyPath] ->
      -- Load the ontology only to confirm it is valid.
      withOntology ontologyPath $ \_ontology ->
        BL8.putStrLn
          ( encode
              OntologyValidationResponse
                { status = "ok"
                }
          )
    ["inspect-ontology-json", "--ontology", ontologyPath] ->
      -- Expose a model-facing catalog from the validated Haskell ontology.
      withOntology ontologyPath emitOntologyCatalog
    ["plan-query-json", "--ontology", ontologyPath, "--query-json", queryJson] -> do
      -- Older/lower-level path: Python already has typed query JSON.
      withOntology ontologyPath $ \ontology ->
        runPlannerFromQueryJson ontology (pack queryJson)
    ["plan-semantic-draft-json", "--ontology", ontologyPath, "--draft-json", draftJson] -> do
      -- Main CLI path: Python sends a loose LLM semantic draft for Haskell to ground.
      withOntology ontologyPath $ \ontology ->
        runPlannerFromSemanticDraftJson ontology (pack draftJson)
    _ ->
      die
        "Usage: cabal run ontology-hs -- validate-ontology-json --ontology <path>\n\
        \   or: cabal run ontology-hs -- inspect-ontology-json --ontology <path>\n\
        \   or: cabal run ontology-hs -- plan-query-json --ontology <path> --query-json <json>\n\
        \   or: cabal run ontology-hs -- plan-semantic-draft-json --ontology <path> --draft-json <json>"

withOntology :: FilePath -> (Ontology -> IO ()) -> IO ()
withOntology ontologyPath action = do
  -- Read semantic-gold.yaml and turn it into validated Haskell ontology values.
  loaded <- loadOntologyEither ontologyPath
  case loaded of
    Right ontology -> action ontology
    Left err -> emitError "OntologyLayer.Validation" err

runPlannerFromQueryJson :: Ontology -> Text -> IO ()
runPlannerFromQueryJson ontology queryJson =
  -- Decode typed Query IR JSON and send it straight into validation/planning.
  case eitherDecodeStrict' (encodeUtf8 queryJson) of
    Left err -> emitError "Planner.Decode" (pack err)
    Right plannedQuery -> emitPlannedQuery ontology plannedQuery

runPlannerFromSemanticDraftJson :: Ontology -> Text -> IO ()
runPlannerFromSemanticDraftJson ontology draftJson =
  -- Decode the loose semantic draft from Python.
  case eitherDecodeStrict' (encodeUtf8 draftJson) of
    Left err -> emitError "SemanticDraft.Decode" (pack err)
    Right semanticDraft ->
      -- Ask QueryModel.SemanticDraft to turn user-facing intent into typed Query IR.
      case semanticDraftToQuery ontology (semanticDraft :: SemanticDraft) of
        Left err -> emitError "QueryModel.SemanticDraft" err
        Right plannedQuery -> emitPlannedQuery ontology plannedQuery

emitPlannedQuery :: Ontology -> Query -> IO ()
emitPlannedQuery ontology plannedQuery =
  -- Validate that the typed query is legal against the ontology.
  case validateQuery ontology plannedQuery of
    Left err -> emitError "GroundedPlanning.Validation" err
    Right () ->
      -- Resolve concrete objects, metrics, dimensions, filters, and join paths.
      case resolveQuery ontology plannedQuery of
        Left err -> emitError "GroundedPlanning.Resolve" err
        Right resolved -> do
          -- Compile the resolved query into runtime steps, then print JSON for Python.
          let executionPlan = compileExecutionPlan resolved
              output =
                PlannerOutput
                  { query_type = renderQueryKindFromQuery plannedQuery
                  , query = plannedQuery
                  , resolved_query = resolved
                  , execution_plan = executionPlan
                  }
          BL8.putStrLn (encode output)

emitError :: Text -> Text -> IO ()
emitError stageName err = do
  -- Print machine-readable error JSON and exit non-zero so Python can raise.
  BL8.putStrLn (encode (PlannerError stageName err))
  exitFailure

renderQueryKindFromQuery :: Query -> Text
renderQueryKindFromQuery query =
  -- Convert the Haskell query constructor into a small debug label.
  case query of
    MetricQuery _ -> "MetricQuery"
    ObjectQuery _ -> "ObjectQuery"
    FindQuery _ -> "FindQuery"

emitOntologyCatalog :: Ontology -> IO ()
emitOntologyCatalog ontology =
  BL8.putStrLn $
    encode $
      Aeson.object
        [ "status" Aeson..= ("ok" :: Text)
        , "subjects" Aeson..= fmap subjectItem subjectObjects
        , "fact_surfaces" Aeson..= fmap factSurfaceItem factObjects
        , "metrics" Aeson..= concatMap metricItems (objects ontology)
        , "dimensions" Aeson..= concatMap dimensionItems (objects ontology)
        , "filters" Aeson..= concatMap filterItems (objects ontology)
        , "time_grains" Aeson..= concatMap timeGrainItems (objects ontology)
        ]
  where
    subjectObjects = filter (not . isFactSurface) (objects ontology)
    factObjects = filter isFactSurface (objects ontology)

subjectItem :: Object -> Aeson.Value
subjectItem obj =
  Aeson.object
    [ "key" Aeson..= objectName obj
    , "label" Aeson..= objectName obj
    , "backing_table" Aeson..= backing_table obj
    , "description" Aeson..= description obj
    , "attribute_count" Aeson..= length (attributes obj)
    , "metric_count" Aeson..= length (metrics obj)
    ]

factSurfaceItem :: Object -> Aeson.Value
factSurfaceItem obj =
  Aeson.object
    [ "key" Aeson..= objectName obj
    , "label" Aeson..= objectName obj
    , "subject" Aeson..= subjectForFactSurface (objectName obj)
    , "backing_table" Aeson..= backing_table obj
    , "grain" Aeson..= grainForFactSurface (objectName obj)
    , "metric_count" Aeson..= length (metrics obj)
    ]

metricItems :: Object -> [Aeson.Value]
metricItems obj =
  fmap
    ( \metric ->
        Aeson.object
          [ "key" Aeson..= metricName metric
          , "label" Aeson..= metricName metric
          , "fact_object" Aeson..= objectName obj
          , "backing_table" Aeson..= backing_table obj
          , "aggregation" Aeson..= aggregation metric
          , "source_attributes" Aeson..= source_attributes metric
          , "executable" Aeson..= executable metric
          , "ranking_polarity" Aeson..= ranking_polarity metric
          , "aliases" Aeson..= metric_aliases metric
          ]
    )
    (metrics obj)

dimensionItems :: Object -> [Aeson.Value]
dimensionItems obj =
  [ attributeItem obj attr
  | attr <- attributes obj
  , kind attr == Dimension || kind attr == PrimaryKey
  ]

filterItems :: Object -> [Aeson.Value]
filterItems obj =
  [ attributeItem obj attr
  | attr <- attributes obj
  , visibility attr == Public
  ]

timeGrainItems :: Object -> [Aeson.Value]
timeGrainItems obj =
  [ attributeItem obj attr
  | attr <- attributes obj
  , attributeName attr `elem` timeAttributeNames
  ]

attributeItem :: Object -> Attribute -> Aeson.Value
attributeItem obj attr =
  Aeson.object
    [ "key" Aeson..= attributeName attr
    , "label" Aeson..= attributeName attr
    , "object" Aeson..= objectName obj
    , "backing_table" Aeson..= backing_table obj
    , "kind" Aeson..= renderAttributeKind (kind attr)
    , "source_column" Aeson..= source_column attr
    , "visibility" Aeson..= renderVisibility (visibility attr)
    , "comparison_identity" Aeson..= comparison_identity attr
    , "aliases" Aeson..= semantic_aliases attr
    , "value_alias_count" Aeson..= length (value_aliases attr)
    ]

objectName :: Object -> Text
objectName Object {name = value} = value

attributeName :: Attribute -> Text
attributeName Attribute {name = value} = value

metricName :: MetricDef -> Text
metricName MetricDef {name = value} = value

isFactSurface :: Object -> Bool
isFactSurface obj = not (null (metrics obj))

subjectForFactSurface :: Text -> Text
subjectForFactSurface factName
  | "Team" `textPrefixOf` factName = "Team"
  | "Player" `textPrefixOf` factName = "Player"
  | otherwise = factName

grainForFactSurface :: Text -> Text
grainForFactSurface factName
  | "Game" `textInfixOf` factName = "game"
  | "Season" `textInfixOf` factName = "season"
  | otherwise = "unknown"

renderAttributeKind :: AttributeKind -> Text
renderAttributeKind attrKind =
  case attrKind of
    PrimaryKey -> "primary_key"
    Dimension -> "dimension"
    Measure -> "measure"

renderVisibility :: AttributeVisibility -> Text
renderVisibility attrVisibility =
  case attrVisibility of
    Public -> "public"
    Internal -> "internal"

timeAttributeNames :: [Text]
timeAttributeNames =
  [ "game_date"
  , "game_month"
  , "game_year"
  , "game_year_month"
  , "season_year"
  , "season_type"
  ]

textPrefixOf :: Text -> Text -> Bool
textPrefixOf = Text.isPrefixOf

textInfixOf :: Text -> Text -> Bool
textInfixOf = Text.isInfixOf
