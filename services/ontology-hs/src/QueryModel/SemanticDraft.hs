-- Purpose:
-- Normalize an LLM-produced semantic draft into typed Query IR through ontology grounding.
--
-- This module is intentionally a small public doorway. The implementation lives
-- in QueryModel.SemanticConstruction.* modules by construction responsibility.

{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft
  ( SemanticDraft
  , semanticDraftToQuery
  ) where

import Data.Text (Text)
import OntologyLayer.Types (Ontology)
import qualified QueryModel.IR as QI
import QueryModel.SemanticConstruction.Build.Aggregate (semanticAggregateDraftToQuery)
import QueryModel.SemanticConstruction.Build.Compare (semanticCompareDraftToQuery)
import QueryModel.SemanticConstruction.Build.Find (semanticFindDraftToQuery)
import QueryModel.SemanticConstruction.Build.Object (semanticObjectDraftToQuery)
import QueryModel.SemanticConstruction.Build.Rank (semanticRankDraftToQuery)
import QueryModel.SemanticConstruction.Build.Trend (semanticTrendDraftToQuery)
import QueryModel.SemanticDraft.Normalize (draftTask)
import QueryModel.SemanticDraft.Types

semanticDraftToQuery :: Ontology -> SemanticDraft -> Either Text QI.Query
semanticDraftToQuery ontology draft = do
  -- Look at the question family captured by the LLM draft.
  -- Implemented families are normalized through ontology grounding here.
  case draftTask (task draft) of
    DraftRank -> semanticRankDraftToQuery ontology draft
    DraftTrend -> semanticTrendDraftToQuery ontology draft
    DraftAggregate -> semanticAggregateDraftToQuery ontology draft
    DraftFind -> semanticFindDraftToQuery ontology draft
    DraftCompare -> semanticCompareDraftToQuery ontology draft
    DraftObject -> semanticObjectDraftToQuery ontology draft
    DraftUnknown rawTask ->
      Left
        ( "Unknown semantic draft task '"
            <> rawTask
            <> "'. Expected one of rank, trend, aggregate, find, compare, or object."
        )
