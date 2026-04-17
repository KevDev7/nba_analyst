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

import Data.Aeson (ToJSON, encode)
import qualified Data.ByteString.Lazy.Char8 as BL8
import Data.Text (Text, pack)
import GHC.Generics (Generic)
import GroundedPlanning.Compile (compileExecutionPlan)
import GroundedPlanning.Plan (ExecutionPlan)
import GroundedPlanning.Resolve (ResolvedQuery, resolveQuery)
import GroundedPlanning.Validation (validateQuery)
import OntologyLayer.Load (loadOntology)
import OntologyLayer.Types (Ontology)
import QueryModel.Build (buildQuery)
import QueryModel.Classify (QueryKind (MetricQueryKind, ObjectQueryKind), classifyQuestion)
import QueryModel.IR (Query)
import QueryModel.Interpret (interpretQuestion)
import QueryModel.Match (matchQuestion)
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
    ["plan", "--ontology", ontologyPath, "--question", question] -> do
      ontology <- loadOntology ontologyPath
      runPlanner ontology (pack question)
    _ ->
      die "Usage: cabal run ontology-hs -- plan --ontology <path> --question <text>"

runPlanner :: Ontology -> Text -> IO ()
runPlanner ontology question =
  case interpretQuestion question of
    Left err -> emitError "QueryModel.Interpret" err
    Right interpreted ->
      case matchQuestion ontology interpreted of
        Left err -> emitError "QueryModel.Match" err
        Right matched ->
          case classifyQuestion interpreted matched of
            Left err -> emitError "QueryModel.Classify" err
            Right queryKind ->
              case buildQuery queryKind interpreted matched of
                Left err -> emitError "QueryModel.Build" err
                Right plannedQuery ->
                  case validateQuery ontology plannedQuery of
                    Left err -> emitError "GroundedPlanning.Validation" err
                    Right () ->
                      case resolveQuery ontology plannedQuery of
                        Left err -> emitError "GroundedPlanning.Resolve" err
                        Right resolved -> do
                          let executionPlan = compileExecutionPlan resolved
                              output =
                                PlannerOutput
                                  { query_type = renderQueryKind queryKind
                                  , query = plannedQuery
                                  , resolved_query = resolved
                                  , execution_plan = executionPlan
                                  }
                          BL8.putStrLn (encode output)

emitError :: Text -> Text -> IO ()
emitError stageName err = do
  BL8.putStrLn (encode (PlannerError stageName err))
  exitFailure

renderQueryKind :: QueryKind -> Text
renderQueryKind queryKind =
  case queryKind of
    MetricQueryKind -> "MetricQuery"
    ObjectQueryKind -> "ObjectQuery"
