-- Purpose:
-- Capture loose semantic intent from a natural-language user question before it
-- is grounded to concrete ontology concepts.
--
-- Uses:
-- - raw user language
-- - optional NLP / model-assisted extraction
--
-- Produces:
-- - a best-effort semantic intent that is not yet committed to exact ontology
--   objects, metrics, dimensions, or paths
--
-- Next:
-- - QueryModel/Ground.hs

{-# LANGUAGE DeriveAnyClass #-}
{-# LANGUAGE DeriveGeneric #-}

module QueryModel.Intent where

import Data.Text (Text)
import GHC.Generics (Generic)

data OrderingDirection
  = IntentAscending
  | IntentDescending
  deriving (Show, Eq, Generic)

data OrderingHint = OrderingHint
  { direction :: OrderingDirection
  , target :: Maybe Text
  }
  deriving (Show, Eq, Generic)

data ComparisonHint = ComparisonHint
  { targetObjectHint :: Maybe Text
  , entityMentions :: [Text]
  }
  deriving (Show, Eq, Generic)

data QueryIntent = QueryIntent
  { rawQuestion :: Text
  , objectMentions :: [Text]
  , metricMentions :: [Text]
  , dimensionMentions :: [Text]
  , filterMentions :: [Text]
  , timeMentions :: [Text]
  , orderingHint :: Maybe OrderingHint
  , limitHint :: Maybe Int
  , comparisonHint :: Maybe ComparisonHint
  }
  deriving (Show, Eq, Generic)

emptyIntent :: Text -> QueryIntent
emptyIntent questionText =
  QueryIntent
    { rawQuestion = questionText
    , objectMentions = []
    , metricMentions = []
    , dimensionMentions = []
    , filterMentions = []
    , timeMentions = []
    , orderingHint = Nothing
    , limitHint = Nothing
    , comparisonHint = Nothing
    }
