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
{-# LANGUAGE OverloadedStrings #-}

module Main where

import Data.Aeson (ToJSON, encode, eitherDecodeStrict')
import qualified Data.ByteString.Lazy.Char8 as BL8
import Data.Text (Text, pack)
import Data.Text.Encoding (encodeUtf8)
import GHC.Generics (Generic)
import GroundedPlanning.Compile (compileExecutionPlan)
import GroundedPlanning.Plan (ExecutionPlan)
import GroundedPlanning.Resolve (ResolvedQuery, resolveQuery)
import GroundedPlanning.Validation (validateQuery)
import OntologyLayer.Load (loadOntology)
import OntologyLayer.Types (Ontology)
import QueryModel.IR (Query (MetricQuery, ObjectQuery))
import System.Environment (getArgs)
import System.Exit (die, exitFailure)

data PlannerOutput = PlannerOutput
  { query_type :: Text
  , query :: Query
  , resolved_query :: ResolvedQuery
  , execution_plan :: ExecutionPlan
  }
  deriving (Show, Generic)

instance ToJSON PlannerOutput

data PlannerError = PlannerError
  { stage :: Text
  , message :: Text
  }
  deriving (Show, Generic)

instance ToJSON PlannerError

main :: IO ()
main = do
  args <- getArgs
  case args of
    ["plan-query-json", "--ontology", ontologyPath, "--query-json", queryJson] -> do
      ontology <- loadOntology ontologyPath
      runPlannerFromQueryJson ontology (pack queryJson)
    _ ->
      die "Usage: cabal run ontology-hs -- plan-query-json --ontology <path> --query-json <json>"

runPlannerFromQueryJson :: Ontology -> Text -> IO ()
runPlannerFromQueryJson ontology queryJson =
  case eitherDecodeStrict' (encodeUtf8 queryJson) of
    Left err -> emitError "Planner.Decode" (pack err)
    Right plannedQuery -> emitPlannedQuery ontology plannedQuery

emitPlannedQuery :: Ontology -> Query -> IO ()
emitPlannedQuery ontology plannedQuery =
  case validateQuery ontology plannedQuery of
    Left err -> emitError "GroundedPlanning.Validation" err
    Right () ->
      case resolveQuery ontology plannedQuery of
        Left err -> emitError "GroundedPlanning.Resolve" err
        Right resolved -> do
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
  BL8.putStrLn (encode (PlannerError stageName err))
  exitFailure

renderQueryKindFromQuery :: Query -> Text
renderQueryKindFromQuery query =
  case query of
    MetricQuery _ -> "MetricQuery"
    ObjectQuery _ -> "ObjectQuery"
