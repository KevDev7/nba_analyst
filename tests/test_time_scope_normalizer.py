from __future__ import annotations

import unittest

from apps.cli.time_scope_normalizer import normalize_question_time_window


class TimeScopeNormalizerTests(unittest.TestCase):
    def test_between_iso_dates(self) -> None:
        window = normalize_question_time_window("Find Lakers games between 2025-01-01 and 2025-02-01")

        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.kind, "between_dates")
        self.assertEqual(window.value, "2025-01-01 to 2025-02-01")

    def test_between_month_names_with_year_on_end_date(self) -> None:
        window = normalize_question_time_window("Find Lakers games between Jan 1 and Feb 1 2025")

        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.kind, "between_dates")
        self.assertEqual(window.value, "2025-01-01 to 2025-02-01")

    def test_from_to_month_names_with_ordinal_suffixes(self) -> None:
        window = normalize_question_time_window("Show team points from January 1st to February 1st, 2025")

        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.kind, "between_dates")
        self.assertEqual(window.value, "2025-01-01 to 2025-02-01")

    def test_since_text_date(self) -> None:
        window = normalize_question_time_window("Show monthly team wins since Jan 1 2025")

        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.kind, "since_date")
        self.assertEqual(window.value, "2025-01-01")

    def test_until_slash_date_with_short_year(self) -> None:
        window = normalize_question_time_window("Find Lakers games before 2/1/25")

        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.kind, "until_date")
        self.assertEqual(window.value, "2025-02-01")

    def test_yearless_single_date_is_not_guessed(self) -> None:
        self.assertIsNone(normalize_question_time_window("Show monthly team wins since Jan 1"))

    def test_fuzzy_event_date_is_not_guessed(self) -> None:
        self.assertIsNone(normalize_question_time_window("Find Lakers games before Christmas"))


if __name__ == "__main__":
    unittest.main()
