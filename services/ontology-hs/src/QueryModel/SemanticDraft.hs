-- Purpose:
-- Normalize an LLM-produced semantic draft into typed Query IR through ontology grounding.
--
-- This module is intentionally a small public doorway. The implementation lives
-- in QueryModel.SemanticDraft.* modules by responsibility/family.

{-# LANGUAGE OverloadedStrings #-}

module QueryModel.SemanticDraft
  ( SemanticDraft
  , semanticDraftToQuery
  ) where

import Data.Text (Text)
import OntologyLayer.Types (Ontology)
import qualified QueryModel.IR as QI
import QueryModel.SemanticDraft.Aggregate (semanticAggregateDraftToQuery)
import QueryModel.SemanticDraft.Compare (semanticCompareDraftToQuery)
import QueryModel.SemanticDraft.Find (semanticFindDraftToQuery)
import QueryModel.SemanticDraft.Normalize (draftTask)
import QueryModel.SemanticDraft.Object (semanticObjectDraftToQuery)
import QueryModel.SemanticDraft.Rank (semanticRankDraftToQuery)
import QueryModel.SemanticDraft.Trend (semanticTrendDraftToQuery)
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
