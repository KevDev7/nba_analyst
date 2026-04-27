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
    PlanFindFilter,
    PlanFindPredicate,
    PlanLinkedFilter,
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

    def test_ranking_interpretation_includes_linked_team_filter(self) -> None:
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
            linked_filters=[
                PlanLinkedFilter(
                    target_object="Team",
                    attribute="team_name",
                    value="Lakers",
                )
            ],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Ranked players by average points for the Lakers over the last 10 games.",
        )

    def test_aggregate_interpretation_includes_generic_linked_filter(self) -> None:
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
            linked_filters=[
                PlanLinkedFilter(
                    target_object="Team",
                    attribute="conference",
                    value="Western",
                )
            ],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Average points by player where team conference equals Western over the last 10 games.",
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

    def test_object_rows_interpretation_includes_linked_team_filter(self) -> None:
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
            linked_filters=[
                PlanLinkedFilter(
                    target_object="Team",
                    attribute="team_name",
                    value="Knicks",
                )
            ],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Players and their total points for the Knicks over the last 10 games.",
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
            find_predicates=[
                PlanFindPredicate(
                    target_object="Team",
                    attribute="team_name",
                    operator="=",
                    value="Lakers",
                ),
                PlanFindPredicate(
                    target_object="TeamGame",
                    attribute="score",
                    operator=">",
                    value=120,
                ),
            ],
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
            find_predicates=[
                PlanFindPredicate(
                    target_object="Team",
                    attribute="team_name",
                    operator="=",
                    value="Lakers",
                ),
                PlanFindPredicate(
                    target_object="TeamGame",
                    attribute="score",
                    operator=">",
                    value=120,
                ),
            ],
        )

        self.assertEqual(
            build_interpretation(payload),
            "Games where team name equals Lakers and score is greater than 120 across all available data.",
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
            find_predicates=[
                PlanFindPredicate(
                    target_object="Team",
                    attribute="team_name",
                    operator="=",
                    value="Lakers",
                )
            ],
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


if __name__ == "__main__":
    unittest.main()
