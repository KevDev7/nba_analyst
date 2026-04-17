-- Purpose:
-- Choose the top-level query shape for the parsed and matched question.
--
-- Uses:
-- - parsed question output from Interpret.hs
-- - matched concepts from Match.hs
--
-- Produces:
-- - the top-level query-kind decision for supported slices
--
-- Next:
-- - Build.hs

{-# LANGUAGE OverloadedStrings #-}

module QueryModel.Classify where

import Data.Text (Text)
import QueryModel.Interpret (ParsedQuestion (..))
import QueryModel.Match (MatchResult)

data QueryKind
  = ObjectQueryKind
  | MetricQueryKind
  deriving (Show, Eq)

classifyQuestion :: ParsedQuestion -> MatchResult -> Either Text QueryKind
classifyQuestion parsedQuestion _matched
  | extractedWindowGames parsedQuestion <= 0 = Left "The query requires a positive last-N-games window."
  | comparisonRequested parsedQuestion = Right MetricQueryKind
  | objectRowsRequested parsedQuestion = Right ObjectQueryKind
  | otherwise = Right MetricQueryKind
