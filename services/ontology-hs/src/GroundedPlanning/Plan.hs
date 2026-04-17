-- Purpose:
-- Define the execution-plan ADTs produced by grounded planning.
--
-- Uses:
-- - compiled SQL generated from resolved queries
--
-- Produces:
-- - JSON-serializable execution plans for the Python runtime
--
-- Next:
-- - services/runtime-py/runtime/AnalysisRuntime/models.py

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}

module GroundedPlanning.Plan where

import Data.Aeson (FromJSON, ToJSON)
import Data.Text (Text)
import GHC.Generics (Generic)

data PlanStep = PlanStep
  { kind :: Text
  , sql :: Maybe Text
  , analysis_spec :: Maybe Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ExecutionPlan = ExecutionPlan
  { plan_type :: Text
  , query_kind :: Text
  , result_shape :: Text
  , entity_label_singular :: Text
  , entity_label_plural :: Text
  , context_label :: Text
  , metric :: Text
  , window_games :: Int
  , time_grain :: Maybe Text
  , time_filter :: Maybe Text
  , season_label :: Maybe Text
  , season_type :: Maybe Text
  , limit :: Int
  , assumptions :: [Text]
  , steps :: [PlanStep]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)
