from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "services" / "runtime-py"
if str(RUNTIME_ROOT) not in sys.path:
    sys.path.insert(0, str(RUNTIME_ROOT))

from runtime.AnalysisRuntime.models import (
    AggregateRow,
    ComparisonEntityStats,
    ComparisonResult,
    ObjectRow,
    PlanDisplayMetadata,
    PlanDisplayMetric,
    PlanFindFilter,
    PlanFindOrder,
    PlanGroupingColumn,
    RankingRow,
    TimeSeriesRow,
)
from runtime.AnswerSynthesis.format_response import format_response
from runtime.AnswerSynthesis.interpretation_summary import build_interpretation
from runtime.AnswerSynthesis.response_models import FinalAnswer, SynthesisPayload
from runtime.AnswerSynthesis.synthesize import synthesize_answer


class InterpretationSummaryTests(unittest.TestCase):
    def test_ranking_interpretation_includes_limit_metric_and_season(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=0,
            season_label="2024-25",
            season_type="regular_season",
            limit=10,
            rows=[RankingRow(rank=1, entity_name="Stephen Curry", metric_value=29.4)],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Top 10 players by average points in the 2024-25 regular season.",
        )

    def test_ranking_interpretation_composes_recent_window_and_season(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=8,
            season_label="2024-25",
            season_type="regular_season",
            limit=10,
            rows=[RankingRow(rank=1, entity_name="Stephen Curry", metric_value=29.1)],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Top 10 players by average points over the last 8 games in the 2024-25 regular season.",
        )

    def test_bottom_ranking_interpretation_uses_ascending_direction(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            metric_order_direction="ASC",
            window_games=10,
            limit=10,
            rows=[RankingRow(rank=1, entity_name="Abdul Gaddy", metric_value=0.0)],
        )

        answer = synthesize_answer(payload)

        self.assertEqual(
            build_interpretation(payload),
            "Bottom 10 players by average points over the last 10 games.",
        )
        self.assertEqual(
            answer.summary,
            "Bottom 10 players by average points over the last 10 games: Abdul Gaddy is lowest with 0.0 average points.",
        )

    def test_player_by_team_grouping_uses_distinct_grouping_labels(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=0,
            season_label="2025-26",
            season_type="regular_season",
            limit=0,
            rows=[
                RankingRow(
                    rank=1,
                    entity_name="Luka Dončić",
                    context_value="LAL",
                    group_values={"group_1": "Luka Dončić", "group_2": "Lakers"},
                    games_played=62,
                    metric_value=33.7,
                )
            ],
            grouping_columns=[
                PlanGroupingColumn(column_key="group_1", label="full_name"),
                PlanGroupingColumn(column_key="group_2", label="team_name"),
            ],
            display_metadata=[
                PlanDisplayMetadata(column_key="games_played", label="Games Played", column_type="analytical_metadata"),
            ],
        )

        answer = synthesize_answer(payload)
        formatted = format_response(answer)

        self.assertEqual(
            build_interpretation(payload),
            "Ranked player and team combinations by average points in the 2025-26 regular season.",
        )
        self.assertIn(
            "Player and team combinations ranked by average points in the 2025-26 regular season",
            answer.summary,
        )
        self.assertIn("Rank | Player | Team | Abbrev | Season | Season Type | Games Played | Average Points", formatted)
        self.assertIn("1 | Luka Dončić | Lakers | LAL | 2025-26 | Regular Season | 62 | 33.7", formatted)

    def test_aggregate_interpretation_includes_grouping_and_season(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="aggregate",
            entity_label_singular="Team",
            entity_label_plural="Teams",
            context_label="Abbrev",
            metric="average_points",
            window_games=0,
            season_label="2024-25",
            season_type="regular_season",
            limit=0,
            aggregate_rows=[AggregateRow(entity_name="Warriors", metric_value=118.1)],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Average points by team in the 2024-25 regular season.",
        )

    def test_ranking_interpretation_includes_row_predicate_team_filter(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=10,
            limit=0,
            rows=[RankingRow(rank=1, entity_name="Luka Dončić", metric_value=39.7)],
            row_predicate={
                "kind": "leaf",
                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                "operator": "equals",
                "value": {"kind": "scalar", "value": "Lakers"},
            },
        )

        self.assertEqual(
            build_interpretation(payload),
            "Ranked players by average points where team name equals Lakers over the last 10 games.",
        )

    def test_aggregate_interpretation_includes_generic_row_predicate_filter(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="aggregate",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=10,
            limit=0,
            aggregate_rows=[AggregateRow(entity_name="Stephen Curry", metric_value=29.4)],
            row_predicate={
                "kind": "leaf",
                "field": {"targetObject": "Team", "attribute": "conference", "location": "row"},
                "operator": "equals",
                "value": {"kind": "scalar", "value": "Western"},
            },
        )

        self.assertEqual(
            build_interpretation(payload),
            "Average points by player where conference equals Western over the last 10 games.",
        )

    def test_ranking_interpretation_preserves_result_predicate_tree_logic(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=10,
            limit=0,
            rows=[RankingRow(rank=1, entity_name="Stephen Curry", metric_value=29.4)],
            result_predicate={
                "kind": "or",
                "predicates": [
                    {
                        "kind": "leaf",
                        "field": {"targetObject": "", "attribute": "average_points", "location": "result"},
                        "operator": "between",
                        "value": {"kind": "range", "lower": 20, "upper": 30},
                    },
                    {
                        "kind": "leaf",
                        "field": {"targetObject": "", "attribute": "average_minutes", "location": "result"},
                        "operator": "greater_than",
                        "value": {"kind": "scalar", "value": 32},
                    },
                ],
            },
        )

        self.assertEqual(
            build_interpretation(payload),
            "Ranked players by average points where (average points is between 20 and 30 or average minutes is greater than 32) over the last 10 games.",
        )

    def test_time_series_interpretation_includes_grain_and_season_type(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="time_series",
            entity_label_singular="Team",
            entity_label_plural="Teams",
            context_label="Abbrev",
            metric="average_points",
            window_games=0,
            time_grain="season",
            time_filter="season_type",
            season_type="regular_season",
            limit=0,
            time_series_rows=[
                TimeSeriesRow(time_bucket="2024-25", series_name="Warriors", metric_value=118.1)
            ],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Average points by team by season for regular seasons.",
        )

    def test_time_series_interpretation_includes_exact_season_scope(self) -> None:
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="time_series",
            entity_label_singular="Team",
            entity_label_plural="Teams",
            context_label="Abbrev",
            metric="average_points",
            window_games=0,
            time_grain="month",
            time_filter="exact_season+season_type",
            season_label="2025-26",
            season_type="regular_season",
            limit=0,
            time_series_rows=[
                TimeSeriesRow(time_bucket="2025-10", series_name="Warriors", metric_value=118.1)
            ],
        )

        answer = synthesize_answer(payload)

        self.assertEqual(
            build_interpretation(payload),
            "Average points by team by month in the 2025-26 regular season.",
        )
        self.assertEqual(
            answer.summary,
            "Monthly average points by team in the 2025-26 regular season are shown below.",
        )

    def test_comparison_interpretation_includes_entities_metric_and_window(self) -> None:
        comparison = ComparisonResult(
            leader="Stephen Curry",
            metric_differential=2.4,
            entity_a=ComparisonEntityStats(
                entity_id=201939,
                entity_name="Stephen Curry",
                metric_value=30.2,
                games_count=10,
            ),
            entity_b=ComparisonEntityStats(
                entity_id=2544,
                entity_name="LeBron James",
                metric_value=27.8,
                games_count=10,
            ),
        )
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="comparison",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=10,
            limit=0,
            comparison=comparison,
        )

        self.assertEqual(
            build_interpretation(payload),
            "Stephen Curry and LeBron James compared by average points over the last 10 games.",
        )

    def test_comparison_interpretation_composes_recent_window_and_season(self) -> None:
        comparison = ComparisonResult(
            leader="Stephen Curry",
            metric_differential=2.4,
            entity_a=ComparisonEntityStats(
                entity_id=201939,
                entity_name="Stephen Curry",
                metric_value=30.2,
                games_count=8,
            ),
            entity_b=ComparisonEntityStats(
                entity_id=2544,
                entity_name="LeBron James",
                metric_value=27.8,
                games_count=8,
            ),
        )
        payload = SynthesisPayload(
            query_kind="metric_query",
            result_shape="comparison",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=8,
            season_label="2024-25",
            season_type="regular_season",
            limit=0,
            comparison=comparison,
        )

        self.assertEqual(
            build_interpretation(payload),
            "Stephen Curry and LeBron James compared by average points over the last 8 games in the 2024-25 regular season.",
        )

    def test_object_rows_interpretation_includes_metric_and_season(self) -> None:
        payload = SynthesisPayload(
            query_kind="object_query",
            result_shape="object_rows",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="total_points",
            window_games=0,
            season_label="2024-25",
            season_type="playoffs",
            limit=0,
            object_rows=[ObjectRow(entity_id=201939, entity_name="Stephen Curry", metric_value=120)],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Players and their total points in the 2024-25 playoffs.",
        )

    def test_object_rows_interpretation_includes_row_predicate_team_filter(self) -> None:
        payload = SynthesisPayload(
            query_kind="object_query",
            result_shape="object_rows",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="total_points",
            window_games=10,
            limit=0,
            object_rows=[ObjectRow(entity_id=1628973, entity_name="Jalen Brunson", metric_value=269)],
            row_predicate={
                "kind": "leaf",
                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                "operator": "equals",
                "value": {"kind": "scalar", "value": "Knicks"},
            },
        )

        self.assertEqual(
            build_interpretation(payload),
            "Players and their total points where team name equals Knicks over the last 10 games.",
        )

    def test_find_rows_interpretation_includes_grounded_predicates(self) -> None:
        payload = SynthesisPayload(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            context_label="",
            metric="",
            window_games=0,
            limit=5,
            find_rows=[{"game_date": "2025-12-01"}],
            find_predicate_tree={
                "kind": "and",
                "predicates": [
                    {
                        "kind": "leaf",
                        "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                        "operator": "equals",
                        "value": {"kind": "scalar", "value": "Lakers"},
                    },
                    {
                        "kind": "leaf",
                        "field": {"targetObject": "TeamGame", "attribute": "score", "location": "row"},
                        "operator": "greater_than",
                        "value": {"kind": "scalar", "value": 120},
                    },
                ],
            },
            find_filters=[
                PlanFindFilter(filter_kind="exact_season", filter_value="2024-25"),
                PlanFindFilter(filter_kind="season_type", filter_value="regular_season"),
            ],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Games where team name equals Lakers and score is greater than 120 in the 2024-25 regular season.",
        )

    def test_find_rows_interpretation_discloses_all_available_data(self) -> None:
        payload = SynthesisPayload(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            context_label="",
            metric="",
            window_games=0,
            limit=5,
            find_rows=[{"game_date": "2025-12-01"}],
            find_predicate_tree={
                "kind": "and",
                "predicates": [
                    {
                        "kind": "leaf",
                        "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                        "operator": "equals",
                        "value": {"kind": "scalar", "value": "Lakers"},
                    },
                    {
                        "kind": "leaf",
                        "field": {"targetObject": "TeamGame", "attribute": "score", "location": "row"},
                        "operator": "greater_than",
                        "value": {"kind": "scalar", "value": 120},
                    },
                ],
            },
        )

        self.assertEqual(
            build_interpretation(payload),
            "Games where team name equals Lakers and score is greater than 120 across all available data.",
        )

    def test_find_rows_interpretation_includes_order_intent(self) -> None:
        payload = SynthesisPayload(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            context_label="",
            metric="",
            window_games=0,
            limit=5,
            find_rows=[{"game_date": "2025-12-01", "score": 131}],
            find_predicate_tree={
                "kind": "leaf",
                "field": {"targetObject": "TeamGame", "attribute": "score", "location": "row"},
                "operator": "greater_than",
                "value": {"kind": "scalar", "value": 120},
            },
            find_orders=[PlanFindOrder(order_field="score", order_direction="descending")],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Games where score is greater than 120 across all available data sorted by score descending.",
        )

    def test_find_rows_interpretation_includes_multiple_order_fields(self) -> None:
        payload = SynthesisPayload(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            context_label="",
            metric="",
            window_games=0,
            limit=5,
            find_rows=[{"game_date": "2025-12-01", "opponent": "Warriors"}],
            find_orders=[
                PlanFindOrder(order_field="opponent", order_direction="ascending"),
                PlanFindOrder(order_field="game_date", order_direction="descending"),
            ],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Games matching the selected filters across all available data sorted by opponent ascending and game date descending.",
        )

    def test_find_rows_interpretation_includes_predicate_tree_logic(self) -> None:
        payload = SynthesisPayload(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            context_label="",
            metric="",
            window_games=0,
            limit=5,
            find_rows=[{"game_date": "2025-12-01"}],
            find_predicate_tree={
                "kind": "and",
                "predicates": [
                    {
                        "kind": "or",
                        "predicates": [
                            {
                                "kind": "leaf",
                                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                                "operator": "equals",
                                "value": {"kind": "scalar", "value": "Lakers"},
                            },
                            {
                                "kind": "leaf",
                                "field": {"targetObject": "Team", "attribute": "team_name", "location": "row"},
                                "operator": "equals",
                                "value": {"kind": "scalar", "value": "Warriors"},
                            },
                        ],
                    },
                    {
                        "kind": "not",
                        "predicate": {
                            "kind": "leaf",
                            "field": {"targetObject": "TeamGame", "attribute": "score", "location": "row"},
                            "operator": "between",
                            "value": {"kind": "range", "lower": 90, "upper": 100},
                        },
                    },
                ],
            },
        )

        self.assertEqual(
            build_interpretation(payload),
            "Games where ((team name equals Lakers or team name equals Warriors) and not (score is between 90 and 100)) across all available data.",
        )

    def test_empty_find_rows_keep_find_summary_shape(self) -> None:
        payload = SynthesisPayload(
            query_kind="find_query",
            result_shape="find_rows",
            entity_label_singular="Game",
            entity_label_plural="Games",
            context_label="",
            metric="",
            window_games=0,
            limit=0,
        )

        answer = synthesize_answer(payload)

        self.assertEqual(answer.summary, "No matching games were returned.")
        self.assertEqual(answer.result_shape, "find_rows")

    def test_synthesis_summary_composes_recent_window_and_season(self) -> None:
        payload = SynthesisPayload(
            query_kind="object_query",
            result_shape="object_rows",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=8,
            season_label="2024-25",
            season_type="regular_season",
            limit=0,
            object_rows=[
                ObjectRow(
                    entity_id=201939,
                    entity_name="Stephen Curry",
                    context_value="GSW",
                    metric_value=29.1,
                )
            ],
        )

        answer = synthesize_answer(payload)

        self.assertEqual(
            answer.summary,
            "Players ordered by average points over the last 8 games in the 2024-25 regular season: Stephen Curry leads with 29.1 average points.",
        )

    def test_formatted_response_prints_interpretation_before_summary(self) -> None:
        answer = FinalAnswer(
            summary="Top 10 players by average points are shown below.",
            interpretation="Top 10 players by average points in the 2024-25 regular season.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=0,
            season_label="2024-25",
            season_type="regular_season",
            limit=10,
            rows=[RankingRow(rank=1, entity_name="Stephen Curry", metric_value=29.4)],
        )

        formatted = format_response(answer)

        self.assertTrue(
            formatted.startswith(
                "Interpreted as: Top 10 players by average points in the 2024-25 regular season.\n\n"
                "Top 10 players by average points are shown below."
            )
        )

    def test_formatted_response_displays_filter_metadata_before_metric(self) -> None:
        answer = FinalAnswer(
            summary="Teams ordered by wins are shown below.",
            interpretation="Ranked teams by wins where win percentage is greater than 0.6 in the 2025-26 regular season.",
            query_kind="metric_query",
            result_shape="ranking",
            entity_label_singular="Team",
            entity_label_plural="Teams",
            context_label="Abbrev",
            metric="wins",
            window_games=0,
            season_label="2025-26",
            season_type="regular_season",
            limit=0,
            rows=[
                RankingRow(
                    rank=1,
                    entity_name="Oklahoma City Thunder",
                    context_value="OKC",
                    metric_value=34,
                    games_played=40,
                    display_values={"games_played": 40, "result_filter_1": 0.850},
                )
            ],
            display_metadata=[
                PlanDisplayMetadata(
                    column_key="games_played",
                    label="Games Played",
                    column_type="analytical_metadata",
                ),
                PlanDisplayMetadata(
                    column_key="result_filter_1",
                    label="win percentage",
                    column_type="filter_metadata",
                ),
            ],
        )

        formatted = format_response(answer)

        self.assertIn(
            "Rank | Team | Abbrev | Season | Season Type | Games Played | Win Percentage | Wins",
            formatted,
        )
        self.assertIn("1 | Oklahoma City Thunder | OKC | 2025-26 | Regular Season | 40 | 0.850 | 34", formatted)

    def test_formatted_response_displays_multiple_metric_columns_in_plan_order(self) -> None:
        answer = FinalAnswer(
            summary="Players ordered by total points are shown below.",
            interpretation="Players and their total points over the last 10 games.",
            query_kind="object_query",
            result_shape="object_rows",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="total_points",
            window_games=10,
            limit=0,
            rows=[],
            object_rows=[
                ObjectRow(
                    entity_id=201939,
                    entity_name="Stephen Curry",
                    context_value="GSW",
                    metric_value=291,
                    display_values={"metric_value": 291, "metric_2": 54, "metric_3": 63},
                )
            ],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_value", metric="total_points", label="total_points"),
                PlanDisplayMetric(column_key="metric_2", metric="total_rebounds", label="total_rebounds"),
                PlanDisplayMetric(column_key="metric_3", metric="total_assists", label="total_assists"),
            ],
        )

        formatted = format_response(answer)

        self.assertIn("Player | Team | Total Points | Rebounds | Assists", formatted)
        self.assertIn("Stephen Curry | GSW | 291 | 54 | 63", formatted)

    def test_formatted_response_suppresses_metadata_that_duplicates_display_metric(self) -> None:
        answer = FinalAnswer(
            summary="Average points by player are shown below.",
            interpretation="Average points and average minutes by player over the last 10 games.",
            query_kind="metric_query",
            result_shape="aggregate",
            entity_label_singular="Player",
            entity_label_plural="Players",
            context_label="Team",
            metric="average_points",
            window_games=10,
            limit=0,
            rows=[],
            aggregate_rows=[
                AggregateRow(
                    entity_name="Stephen Curry",
                    metric_value=29.1,
                    minutes=31.2,
                    display_values={"minutes": 31.2, "metric_value": 29.1, "metric_2": 31.2},
                )
            ],
            display_metadata=[
                PlanDisplayMetadata(column_key="minutes", label="Minutes", column_type="analytical_metadata"),
            ],
            display_metrics=[
                PlanDisplayMetric(column_key="metric_value", metric="average_points", label="average_points"),
                PlanDisplayMetric(column_key="metric_2", metric="average_minutes", label="average_minutes"),
            ],
        )

        formatted = format_response(answer)

        self.assertIn("Player | Average Points | Average Minutes", formatted)
        self.assertNotIn("Player | Minutes | Average Points | Average Minutes", formatted)


if __name__ == "__main__":
    unittest.main()
