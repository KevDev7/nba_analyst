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
{-# LANGUAGE DuplicateRecordFields #-}

module GroundedPlanning.Plan where

import Data.Aeson (FromJSON, ToJSON)
import Data.Text (Text)
import GHC.Generics (Generic)
import QueryModel.IR (FilterValue)

data PlanStep = PlanStep
  { kind :: Text
  , sql :: Maybe Text
  , analysis_spec :: Maybe Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanFindPredicate = PlanFindPredicate
  { target_object :: Text
  , attribute :: Text
  , operator :: Text
  , value :: FilterValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanFindFilter = PlanFindFilter
  { filter_kind :: Text
  , filter_value :: Maybe FilterValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanLinkedFilter = PlanLinkedFilter
  { target_object :: Text
  , attribute :: Text
  , value :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanDisplayMetadata = PlanDisplayMetadata
  { column_key :: Text
  , label :: Text
  , column_type :: Text
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
  , metric_aggregation :: Text
  , window_games :: Int
  , time_grain :: Maybe Text
  , time_filter :: Maybe Text
  , season_label :: Maybe Text
  , season_type :: Maybe Text
  , limit :: Int
  , assumptions :: [Text]
  , find_predicates :: [PlanFindPredicate]
  , find_filters :: [PlanFindFilter]
  , linked_filters :: [PlanLinkedFilter]
  , display_metadata :: [PlanDisplayMetadata]
  , steps :: [PlanStep]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)
