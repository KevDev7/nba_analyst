-- Purpose:
-- Public compile entry point for turning grounded queries into runtime plans.
--
-- The implementation is split into PlanBuilder and SQL renderer modules so this
-- module stays as the small doorway used by Main.hs.

module GroundedPlanning.Compile
  ( compileExecutionPlan
  ) where

import GroundedPlanning.Compile.PlanBuilder (compileExecutionPlan)
