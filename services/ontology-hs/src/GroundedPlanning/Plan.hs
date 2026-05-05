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
{-# LANGUAGE OverloadedStrings #-}

module GroundedPlanning.Plan where

import Data.Aeson (FromJSON, ToJSON (toJSON), object, (.=))
import Data.Text (Text)
import GHC.Generics (Generic)
import QueryModel.IR (FilterValue, Predicate)

data PlanStep = PlanStep
  { kind :: Text
  , sql :: Maybe Text
  , analysis_spec :: Maybe Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanFindFilter = PlanFindFilter
  { filter_kind :: Text
  , filter_value :: Maybe FilterValue
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanFindOrder = PlanFindOrder
  { order_field :: Text
  , order_direction :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanDisplayMetadata = PlanDisplayMetadata
  { column_key :: Text
  , label :: Text
  , column_type :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanDisplayMetric = PlanDisplayMetric
  { column_key :: Text
  , metric :: Text
  , label :: Text
  , aggregation :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data PlanGroupingColumn = PlanGroupingColumn
  { column_key :: Text
  , label :: Text
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data AnswerSubjectContext = AnswerSubjectContext
  { answerSubjectSingular :: Text
  , answerSubjectPlural :: Text
  , answerSubjectContextLabel :: Text
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON AnswerSubjectContext where
  toJSON context =
    object
      [ "singular" .= answerSubjectSingular context
      , "plural" .= answerSubjectPlural context
      , "context_label" .= answerSubjectContextLabel context
      ]

data AnswerMetricContext = AnswerMetricContext
  { answerMetricKey :: Text
  , answerMetricAggregation :: Text
  , answerMetricOrderDirection :: Text
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON AnswerMetricContext where
  toJSON context =
    object
      [ "key" .= answerMetricKey context
      , "aggregation" .= answerMetricAggregation context
      , "order_direction" .= answerMetricOrderDirection context
      ]

data AnswerTimeContext = AnswerTimeContext
  { answerTimeWindowGames :: Int
  , answerTimeGrain :: Maybe Text
  , answerTimeFilter :: Maybe Text
  , answerTimeWindowDays :: Maybe Int
  , answerTimeStartDate :: Maybe Text
  , answerTimeEndDate :: Maybe Text
  , answerTimeSeasonLabel :: Maybe Text
  , answerTimeSeasonType :: Maybe Text
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON AnswerTimeContext where
  toJSON context =
    object
      [ "window_games" .= answerTimeWindowGames context
      , "grain" .= answerTimeGrain context
      , "filter" .= answerTimeFilter context
      , "window_days" .= answerTimeWindowDays context
      , "start_date" .= answerTimeStartDate context
      , "end_date" .= answerTimeEndDate context
      , "season_label" .= answerTimeSeasonLabel context
      , "season_type" .= answerTimeSeasonType context
      ]

data AnswerRankingContext = AnswerRankingContext
  { answerRankingIntentLabel :: Maybe Text
  , answerRankingLimit :: Int
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON AnswerRankingContext where
  toJSON context =
    object
      [ "intent_label" .= answerRankingIntentLabel context
      , "limit" .= answerRankingLimit context
      ]

data AnswerFindContext = AnswerFindContext
  { answerFindPredicateTree :: Maybe Predicate
  , answerFindFilters :: [PlanFindFilter]
  , answerFindOrders :: [PlanFindOrder]
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON AnswerFindContext where
  toJSON context =
    object
      [ "predicate_tree" .= answerFindPredicateTree context
      , "filters" .= answerFindFilters context
      , "orders" .= answerFindOrders context
      ]

data AnswerPredicateContext = AnswerPredicateContext
  { answerRowPredicate :: Maybe Predicate
  , answerResultPredicate :: Maybe Predicate
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON AnswerPredicateContext where
  toJSON context =
    object
      [ "row" .= answerRowPredicate context
      , "result" .= answerResultPredicate context
      ]

data AnswerDisplayContext = AnswerDisplayContext
  { answerGroupingColumns :: [PlanGroupingColumn]
  , answerDisplayMetadata :: [PlanDisplayMetadata]
  , answerDisplayMetrics :: [PlanDisplayMetric]
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON AnswerDisplayContext where
  toJSON context =
    object
      [ "grouping_columns" .= answerGroupingColumns context
      , "metadata" .= answerDisplayMetadata context
      , "metrics" .= answerDisplayMetrics context
      ]

data AnswerContext = AnswerContext
  { answerContextQueryKind :: Text
  , answerContextResultShape :: Text
  , answerContextSubject :: AnswerSubjectContext
  , answerContextMetric :: AnswerMetricContext
  , answerContextTime :: AnswerTimeContext
  , answerContextRanking :: AnswerRankingContext
  , answerContextFind :: AnswerFindContext
  , answerContextPredicates :: AnswerPredicateContext
  , answerContextDisplay :: AnswerDisplayContext
  , answerContextAssumptions :: [Text]
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON AnswerContext where
  toJSON context =
    object
      [ "query_kind" .= answerContextQueryKind context
      , "result_shape" .= answerContextResultShape context
      , "subject" .= answerContextSubject context
      , "metric" .= answerContextMetric context
      , "time" .= answerContextTime context
      , "ranking" .= answerContextRanking context
      , "find" .= answerContextFind context
      , "predicates" .= answerContextPredicates context
      , "display" .= answerContextDisplay context
      , "assumptions" .= answerContextAssumptions context
      ]

data PlanExecutionContext = PlanExecutionContext
  { plan_type :: Text
  , steps :: [PlanStep]
  }
  deriving (Show, Eq, Generic, FromJSON, ToJSON)

data ExecutionPlan = ExecutionPlan
  { execution :: PlanExecutionContext
  , answer_context :: AnswerContext
  }
  deriving (Show, Eq, Generic, FromJSON)

instance ToJSON ExecutionPlan where
  toJSON plan =
    object
      [ "execution" .= execution plan
      , "answer_context" .= answer_context plan
      ]
